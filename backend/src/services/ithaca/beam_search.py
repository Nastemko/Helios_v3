# Copyright 2025 the Aeneas Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Eval utils."""

import time
from typing import List, NamedTuple, Sequence, Union

import jax
import jax.numpy as jnp
import numpy as np
import tqdm

from services.ithaca import text_utils as util_text


def grad_to_saliency_char(gradient_char, text_char_onehot, text_len, alphabet):
    """Generates saliency map."""
    saliency_char = np.linalg.norm(gradient_char, axis=2)[0, : text_len[0]]

    text_char = np.array(text_char_onehot).argmax(axis=-1)
    idx_mask = np.logical_or(
        text_char[0, : text_len[0]] > alphabet.alphabet_end_idx,
        text_char[0, : text_len[0]] < alphabet.alphabet_start_idx,
    )
    idx_unmask = np.logical_not(idx_mask)

    saliency_char_tmp = saliency_char.copy()
    saliency_char_tmp[idx_mask] = 0.0
    if idx_unmask.any():
        saliency_char_tmp[idx_unmask] = (
            saliency_char[idx_unmask] - saliency_char[idx_unmask].min()
        ) / (saliency_char[idx_unmask].max() - saliency_char[idx_unmask].min() + 1e-8)
    return saliency_char_tmp


def softmax(x, axis=-1):
    """Compute softmax values for each sets of scores in x."""
    unnormalized = np.exp(x - x.max(axis, keepdims=True))
    return unnormalized / unnormalized.sum(axis, keepdims=True)


def log_softmax(x, axis=-1):
    """Log-Softmax function."""
    shifted = x - x.max(axis, keepdims=True)
    return shifted - np.log(np.sum(np.exp(shifted), axis, keepdims=True))


def to_nucleus_logits(
    logits: np.ndarray,
    top_p: float,
) -> np.ndarray:
    """Remaps logits for nucleus sampling."""
    clipped_top_p = max(top_p, 5e-6)
    sorted_logits = np.sort(logits)  # , is_stable=False)
    sorted_probs = softmax(sorted_logits)
    threshold_idx = np.argmax(np.cumsum(sorted_probs, -1) >= 1 - clipped_top_p, axis=-1)
    threshold_largest_logits = np.take_along_axis(  # pytype: disable=wrong-arg-types
        sorted_logits, threshold_idx[..., None], axis=-1
    )
    assert threshold_largest_logits.shape == logits.shape[:-1] + (1,)
    logits = np.where(logits >= threshold_largest_logits, logits, -1e12)
    return logits


class BeamEntry(NamedTuple):
    text_pred: str
    mask_idx: Union[set[int], list[int]]
    pred_len: int
    unk_len: int
    pred_logprob: float
    # Trajectory of every intermediate string, consumed only by
    # sequential_restoration_saliency. Building it costs a full list copy per
    # candidate -- ~2900 per generation at beam 35 -- so beam_search_batch only
    # accumulates it when track_history=True. Left empty otherwise.
    text_history: Sequence[str] = ()


def beam_search_batch(
    forward,
    params,
    alphabet,
    text_pred,
    mask_idx,
    vision_img=None,
    vision_available=False,
    beam_width=20,
    temperature=1.0,
    nucleus=False,
    nucleus_top_p=0.95,
    a_penalty=0.6,
    max_len=768,
    max_iterations=None,
    skip_double_space=True,
    display_progress=False,
    sequential_decoding=True,
    track_history=False,
    top_chars=None,
    time_budget=None,
) -> List[BeamEntry]:
    """Non-sequential beam search.

    Args:
      track_history: accumulate each entry's full text trajectory. Only
        sequential_restoration_saliency consumes it, and it costs a list copy
        per candidate, so it is off by default.
      top_chars: if set, expand only this many highest-logprob characters at
        each hole instead of the whole alphabet. The alphabet is 29 branches
        wide for Greek, but candidates outside the top handful essentially
        never survive pruning, so building their strings is wasted work. None
        keeps the exhaustive upstream behaviour.
      time_budget: soft wall-clock limit in seconds. Checked between
        generations, so the actual runtime overshoots by at most one forward
        pass. On expiry the best candidates found so far are returned rather
        than raising -- a slightly shorter answer beats a request that never
        completes.
    """

    mask_idx = set(mask_idx)
    initial_text_pred = text_pred.rstrip(alphabet.pad)
    beam = [
        BeamEntry(
            initial_text_pred,
            mask_idx,
            0,
            0,
            0.0,
            [initial_text_pred] if track_history else (),
        )
    ]
    beam_top = {}

    space_idx = alphabet.char2idx[alphabet.space]

    def _history(entry, text_pred_i):
        """Extend an entry's trajectory, or skip the copy when not tracking."""
        if not track_history:
            return ()
        return list(entry.text_history) + [text_pred_i]

    # Initialise tqdm bar
    if display_progress:
        pbar = tqdm.tqdm(total=len(mask_idx))

    deadline = None if time_budget is None else time.monotonic() + time_budget

    iteration = 0
    while beam and (max_iterations is None or iteration < max_iterations):
        # Checked before the forward pass, which is the expensive part of a
        # generation. Entries still holding a hole are abandoned; anything
        # already complete is in beam_top and is still returned below.
        if deadline is not None and time.monotonic() > deadline:
            break
        iteration += 1
        beam_tmp = []
        beam_batch = []

        text_chars = []

        # Determine the maximum length among all texts
        text_pred_len_max = max(len(entry.text_pred) for entry in beam)

        for entry in beam:
            # Append padding (if needed)
            pad_len = text_pred_len_max - len(entry.text_pred)
            text_pred_pad = entry.text_pred + alphabet.pad * pad_len

            current_mask_idx = (
                entry.mask_idx.copy()
            )  # pytype: disable=attribute-error  # strict_namedtuple_checks
            text_char = util_text.text_to_idx(text_pred_pad, alphabet).reshape(1, -1)
            text_chars.append(text_char)
            beam_batch.append(entry._replace(mask_idx=current_mask_idx))
        text_chars = np.vstack(text_chars)

        batch_size = text_chars.shape[0]
        _, _, mask_logits, _, unk_logits = forward(
            params,
            text_char=text_chars,
            text_char_onehot=None,
            vision_img=(
                None
                if vision_img is None
                else jnp.repeat(vision_img, batch_size, axis=0)
            ),
            vision_available=(
                None
                if vision_available is None
                else jnp.repeat(vision_available, batch_size, axis=0)
            ),
        )

        # Compute log probabilities
        mask_logits = np.array(mask_logits / temperature)
        unk_logits = np.array(unk_logits)

        # Iterate over batch elements
        for batch_i, current_beam_entry in enumerate(beam_batch):
            text_len = len(current_beam_entry.text_pred)

            mask_logits_i = mask_logits[batch_i, :text_len]
            mask_logprob_i = log_softmax(mask_logits_i)
            unk_logprob_i = log_softmax(unk_logits[batch_i, :text_len])
            if nucleus:
                mask_logits_nucleus_i = to_nucleus_logits(mask_logprob_i, nucleus_top_p)

            # Keep only predictions for mask
            mask_idx_loop = []
            for text_char_pos in current_beam_entry.mask_idx:
                # Skip if already restored
                if current_beam_entry.text_pred[text_char_pos] not in [
                    alphabet.missing,
                    alphabet.missing_unk,
                ]:
                    continue
                mask_idx_loop.append(text_char_pos)
            if sequential_decoding:
                mask_idx_loop = sorted(mask_idx_loop)[:1]

            for text_char_pos in mask_idx_loop:
                # Process unknown length missing characters
                if current_beam_entry.text_pred[text_char_pos] == alphabet.missing_unk:
                    # Case: add a missing character and shift all indexes by 1
                    text_pred_i = (
                        current_beam_entry.text_pred[: text_char_pos + 1]
                        + alphabet.missing
                        + current_beam_entry.text_pred[text_char_pos + 1 :]
                    )
                    mask_idx_i = set(
                        m_i + 1 if m_i > text_char_pos else m_i
                        for m_i in current_beam_entry.mask_idx
                    )
                    mask_idx_i.add(text_char_pos + 1)
                    pred_logprob_i = (
                        current_beam_entry.pred_logprob
                        + unk_logprob_i[text_char_pos, 1]
                    )

                    # Skip if it exceeds the maximum length
                    if len(text_pred_i) <= max_len:
                        beam_tmp.append(
                            BeamEntry(
                                text_pred_i,
                                mask_idx_i,
                                current_beam_entry.pred_len,
                                current_beam_entry.unk_len + 1,
                                pred_logprob_i,
                                _history(current_beam_entry, text_pred_i),
                            )
                        )

                    # Case: add a replace missing unk with single missing character
                    mask_idx_i = (
                        current_beam_entry.mask_idx.copy()
                    )  # pytype: disable=attribute-error  # strict_namedtuple_checks
                    text_pred_i = (
                        current_beam_entry.text_pred[:text_char_pos]
                        + alphabet.missing
                        + current_beam_entry.text_pred[text_char_pos + 1 :]
                    )
                    pred_logprob_i = (
                        current_beam_entry.pred_logprob
                        + unk_logprob_i[text_char_pos, 0]
                    )
                    beam_tmp.append(
                        BeamEntry(
                            text_pred_i,
                            mask_idx_i,
                            current_beam_entry.pred_len,
                            current_beam_entry.unk_len + 1,
                            pred_logprob_i,
                            _history(current_beam_entry, text_pred_i),
                        )
                    )
                elif current_beam_entry.text_pred[text_char_pos] == alphabet.missing:
                    # Iterate over possible characters
                    candidate_char_ids = [space_idx] + list(
                        range(
                            alphabet.alphabet_start_idx,
                            alphabet.alphabet_end_idx + 1,
                            # alphabet.char2idx[alphabet.punctuation[-1]] + 1,
                        )
                    )

                    # Restrict to the most likely characters before building any
                    # strings. Every candidate below costs a list copy, a join
                    # and a set copy, and this loop runs beam_width times per
                    # generation -- but only the top few ever survive the
                    # length-normalised pruning at the end of the iteration.
                    # argpartition is O(n) and leaves the kept ids unordered,
                    # which is fine: they are all scored individually anyway.
                    if top_chars is not None and top_chars < len(candidate_char_ids):
                        candidate_logprobs = mask_logprob_i[
                            text_char_pos, candidate_char_ids
                        ]
                        keep = np.argpartition(-candidate_logprobs, top_chars - 1)[
                            :top_chars
                        ]
                        candidate_char_ids = [candidate_char_ids[k] for k in keep]

                    for text_char_id in candidate_char_ids:
                        # Skip expanding the beam if logprob too small
                        if nucleus and np.isclose(
                            mask_logits_nucleus_i[text_char_pos, text_char_id], -1e12
                        ):
                            continue

                        # Create a copy of the text
                        text_pred_i_list = list(current_beam_entry.text_pred)
                        text_pred_i_list[text_char_pos] = alphabet.idx2char[
                            text_char_id
                        ]
                        text_pred_i = "".join(text_pred_i_list)

                        # Ignore possible cases where two spaces are next to each other
                        if text_pred_i_list[text_char_pos] == " " and skip_double_space:
                            if text_char_pos == 0:
                                if text_pred_i_list[text_char_pos + 1] == " ":
                                    continue
                            elif text_char_pos == text_len - 1:
                                if text_pred_i_list[text_char_pos - 1] == " ":
                                    continue
                            elif (
                                text_pred_i_list[text_char_pos + 1] == " "
                                or text_pred_i_list[text_char_pos - 1] == " "
                            ):
                                continue

                        pred_logprob_i = (
                            current_beam_entry.pred_logprob
                            + mask_logprob_i[text_char_pos, text_char_id]
                        )

                        # Check completed condition
                        mask_idx_i = (
                            current_beam_entry.mask_idx.copy()
                        )  # pytype: disable=attribute-error  # strict_namedtuple_checks
                        finished = all(
                            text_pred_i[m_idx]
                            not in {alphabet.missing, alphabet.missing_unk}
                            for m_idx in current_beam_entry.mask_idx
                        )

                        if finished:
                            if (text_pred_i not in beam_top) or (
                                text_pred_i in beam_top
                                and beam_top[text_pred_i].pred_logprob < pred_logprob_i
                            ):
                                beam_top[text_pred_i] = BeamEntry(
                                    text_pred_i,
                                    sorted(mask_idx_i),
                                    current_beam_entry.pred_len + 1,
                                    current_beam_entry.unk_len,
                                    pred_logprob_i,
                                    _history(current_beam_entry, text_pred_i),
                                )
                        else:
                            beam_tmp.append(
                                BeamEntry(
                                    text_pred_i,
                                    mask_idx_i,
                                    current_beam_entry.pred_len + 1,
                                    current_beam_entry.unk_len,
                                    pred_logprob_i,
                                    _history(current_beam_entry, text_pred_i),
                                )
                            )

        # Order all candidates by score
        beam_tmp_kv = {}
        for entry in beam_tmp:
            if (entry.text_pred not in beam_tmp_kv) or (
                entry.text_pred in beam_tmp_kv
                and beam_tmp_kv[entry.text_pred].pred_logprob > entry.pred_logprob
            ):
                beam_tmp_kv[entry.text_pred] = entry
        beam_tmp = sorted(
            list(beam_tmp_kv.values()),
            key=lambda e: e.pred_logprob / (1 + e.pred_len + e.unk_len) ** a_penalty,
            reverse=True,
        )

        # Select top k beams
        beam = beam_tmp[:beam_width]

        # Update progress bar
        if display_progress:
            pbar.update(1)

    # Order final candidates by score
    return sorted(
        list(beam_top.values()),
        key=lambda e: e.pred_logprob / (1 + e.pred_len + e.unk_len) ** a_penalty,
        reverse=True,
    )[:beam_width]


def saliency_loss_subregion(forward, params, text_char_emb, padding, subregion=None):
    """Saliency map for subregion."""

    _, subregion_logits, _, _, _ = forward(
        params,
        text_char_emb=text_char_emb,
        padding=padding,
    )
    if subregion is None:
        subregion = subregion_logits.argmax(axis=-1)[0]
    return subregion_logits[0, subregion]


def saliency_loss_date(forward, params, text_char_emb, padding):
    """saliency_loss_date."""

    date_pred, _, _, _, _ = forward(
        params,
        text_char_emb=text_char_emb,
        padding=padding,
    )

    date_pred_argmax = date_pred.argmax(axis=-1)
    return date_pred[0, date_pred_argmax[0]]


def compute_attribution_saliency_maps(
    text_char,
    text_len,
    padding,
    forward,
    params,
    alphabet,
    vocab_char_size,
    subregion_loss_kwargs=None,
):
    """Compute saliency maps for subregions and dates."""

    if subregion_loss_kwargs is None:
        subregion_loss_kwargs = {}

    # Get saliency gradients
    dtype = params["params"]["char_embeddings"]["embedding"].dtype
    text_char_onehot = jax.nn.one_hot(text_char, vocab_char_size).astype(dtype)
    text_char_emb = jnp.matmul(
        text_char_onehot, params["params"]["char_embeddings"]["embedding"]
    )
    gradient_subregion_char = jax.grad(saliency_loss_subregion, 2)(
        forward, params, text_char_emb, padding, **subregion_loss_kwargs
    )
    gradient_date_char = jax.grad(saliency_loss_date, 2)(
        forward, params, text_char_emb, padding=padding
    )

    # Generate saliency maps for subregions
    input_grad_subregion_char = np.multiply(
        gradient_subregion_char, text_char_emb
    )  # grad x input
    subregion_saliency = grad_to_saliency_char(
        input_grad_subregion_char,
        text_char_onehot,
        text_len=text_len,
        alphabet=alphabet,
    )
    subregion_saliency = subregion_saliency / np.max(subregion_saliency[1:])

    # Generate saliency maps for dates
    input_grad_date_char = np.multiply(
        gradient_date_char, text_char_emb
    )  # grad x input
    date_saliency = grad_to_saliency_char(
        input_grad_date_char,
        text_char_onehot,
        text_len=text_len,
        alphabet=alphabet,
    )
    date_saliency = date_saliency / np.max(date_saliency[1:])

    return date_saliency, subregion_saliency
