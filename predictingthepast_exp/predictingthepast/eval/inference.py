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
"""Module for performing inference using Jax, including decoding.

The module performs the main inference tasks via the functions attribute(),
restore(), and contextualize().

Both take a function called `forward`, a Jax function mapping from model inputs
(including parameters as the first argument) to the model output tuple.
This is in contrast to Ithaca's code which expected a forward function that
already wraps the model params.
"""

import json
import math
import pickle
import re
from typing import NamedTuple, Optional

import jax
import numpy as np
from PIL import Image
from predictingthepast.util import region_names
import predictingthepast.util.eval as eval_util
import predictingthepast.util.text as util_text


class ContextualizationResults(NamedTuple):
  """Similar inscriptions and related information."""

  ids: list[str]  # Inscription IDs
  ids_alt: list[Optional[dict[str, str]]]  # Inscription texts
  text: list[str]  # Inscription texts
  location_ids: list[Optional[int]]  # Location IDs
  date_min: list[Optional[int]]  # Lower bound of date range
  date_max: list[Optional[int]]  # Upper bound of date range
  partner_link: list[Optional[str]]  # Partner link urls when available
  score: list[float]  # Score of the similarity

  def build_json(self):
    return {
        'ids': self.ids,
        'ids_alt': self.ids_alt,
        'text': self.text,
        'location_ids': self.location_ids,
        'date_min': self.date_min,
        'date_max': self.date_max,
        'partner_link': self.partner_link,
        'score': self.score,
    }

  def json(self, **kwargs):
    return json.dumps(self.build_json(), **kwargs)


class LocationPrediction(NamedTuple):
  """One location prediction and its associated probability."""

  location_id: int
  score: float

  def build_json(self):
    return {
        'location_id': self.location_id,
        'score': self.score,
    }


class AttributionResults(NamedTuple):
  """Immediate model output attribution predictions and related information."""

  input_text: str

  # List of pairs of location ID and probability
  locations: list[LocationPrediction]

  # Probabilities over year range [-800, -790, -780, ..., 790, 800]
  year_scores: list[float]  # length 160

  # Per-character saliency maps:
  date_saliency: list[float]
  location_saliency: list[float]  # originally called subregion

  def build_json(self):
    return {
        'input_text': self.input_text,
        'locations': [l.build_json() for l in self.locations],
        'year_scores': self.year_scores,
        'date_saliency': self.date_saliency,
        'location_saliency': self.location_saliency,
    }

  def json(self, **kwargs):
    return json.dumps(self.build_json(), **kwargs)


class Restoration(NamedTuple):
  """One restored candidate string from the beam search."""

  text: str
  restored: list[int]  # char indices that were restored
  score: float

  def build_json(self):
    return {'text': self.text, 'restored': self.restored, 'score': self.score}


class RestorationCharSaliency(NamedTuple):
  """Saliency entry for one predicted character of a prediction."""

  text: str
  restored_idx: int  # which predicted character the saliency map corresponds to
  saliency: list[float]

  def build_json(self):
    return {
        'text': self.text,
        'restored_idx': self.restored_idx,
        'saliency': self.saliency,
    }


class RestorationResults(NamedTuple):
  """Contains all text-related restoration predictions."""

  input_text: str
  top_prediction: str
  missing: list[int]  # char indices with a missing character

  # List of top N results from beam search:
  predictions: list[Restoration]

  # Saliency maps for each successive character of the best (greedy) prediction
  prediction_saliency: list[RestorationCharSaliency]

  def build_json(self):
    return {
        'input_text': self.input_text,
        'top_prediction': self.top_prediction,
        'predictions': [r.build_json() for r in self.predictions],
        'prediction_saliency': [
            m.build_json() for m in self.prediction_saliency
        ],
    }

  def json(self, **kwargs):
    return json.dumps(self.build_json(), **kwargs)


def process_img(img, output_size=(224, 224)):
  """Process image."""
  # Convert to grayscale
  img = img.convert('L')

  # Get image size
  width, height = img.size
  max_side = max(img.size)

  # Create a square canvas with side length max_side
  padded_img = Image.new('L', (max_side, max_side), (0,))

  # Compute padding offsets
  offset_x = (max_side - width) // 2
  offset_y = (max_side - height) // 2

  # Paste image onto canvas
  padded_img.paste(img, (offset_x, offset_y))

  # Crop the image
  cropped_img = padded_img.crop((0, 0, max_side, max_side))

  # Resize
  cropped_img = cropped_img.resize(output_size)

  return cropped_img


# These constants are fixed for all recent versions of the model.
MIN_TEXT_LEN = 25
TEXT_LEN = 768  # fixed model sequence length
DATE_MIN = -800
DATE_MAX = 800
DATE_INTERVAL = 10
RESTORATION_BEAM_WIDTH = 200
RESTORATION_TEMPERATURE = 1.0
UNK_RESTORATION_MAX_LEN = 20
A_PENALTY = 1.0
SEED = 1
ALPHABET_MISSING_RESTORE = '?'  # missing characters to restore
ALPHABET_MISSING_UNK_RESTORE = '#'  # missing characters to restore


def _prepare_text(
    text, alphabet, check_length=True
) -> tuple[str, str, str, np.ndarray, list[int], np.ndarray, list[int]]:
  """Adds start of sequence symbol, and padding.

  Also strips accents if present, trims whitespace, and generates arrays ready
  for input into the model.

  Args:
    text: Raw text input string, no padding or start of sequence symbol.
    alphabet: GreekAlphabet object containing index/character mappings.
    check_length: Whether to check the length of the text.

  Returns:
    Tuple of cleaned text (str), padded text (str), char indices (array of batch
    size 1), word indices (array of batch size 1), text length (list of size 1)
  """
  text = re.sub(r'\s+', ' ', text.strip().lower())
  text = util_text.strip_accents(text)

  if check_length and len(text) < MIN_TEXT_LEN:
    raise ValueError('Input text too short.')

  if check_length and len(text) >= TEXT_LEN:
    raise ValueError('Input text too long.')

  text_sos = alphabet.sos + text
  text_len = [len(text_sos)]  # includes SOS, but not padding

  restore_mask_idx = [
      i
      for i, c in enumerate(text_sos)
      if c in [ALPHABET_MISSING_RESTORE, ALPHABET_MISSING_UNK_RESTORE]
  ]

  text_padded = text_sos.replace(ALPHABET_MISSING_RESTORE, alphabet.missing)
  text_padded = text_padded.replace(
      ALPHABET_MISSING_UNK_RESTORE, alphabet.missing_unk
  )
  text_padded = text_padded + alphabet.pad * max(0, TEXT_LEN - len(text_sos))

  text_char = util_text.text_to_idx(text_padded, alphabet).reshape(1, -1)
  padding = np.where(text_char > 0, 1, 0)

  return (
      text,
      text_sos,
      text_padded,
      text_char,
      text_len,
      padding,
      restore_mask_idx,
  )


def _generate_text_emb(params, forward, alphabet, input_text, emb_mode='avg'):
  """Computes model embeddings for retrieval."""

  # Text preparation and inference
  (_, _, _, text_char, text_len, _, _) = _prepare_text(input_text, alphabet)

  # Generate embeddings
  rng = jax.random.PRNGKey(SEED)
  _, torso_outputs = forward(
      params,
      text_char=text_char,
      output_return_emb=True,
      rngs={'dropout': rng},
      is_training=False,
  )

  if emb_mode == 'first':
    return np.array(torso_outputs[0, 0])
  elif emb_mode == 'avg':
    return np.array(torso_outputs[0, : text_len[0]].mean(0))
  else:
    raise ValueError(f'Unknown emb_mode: {emb_mode}')


def _get_relevant_texts(
    dataset,
    retrieval,
    text_emb,
    exclude_id=None,
    normalize=False,
    include_test=False,
    retrieval_top_k=20,
):
  """Returns retrieval stats for a given text embedding."""
  if normalize:
    text_emb = (text_emb - retrieval['emb_v_mean']) / retrieval['emb_v_std']

  if include_test:
    retrieval_k = retrieval['emb_k_all']
    retrieval_v = retrieval['emb_v_all_normed']
  else:
    retrieval_k = retrieval['emb_k']
    retrieval_v = retrieval['emb_v_normed']

  # Cosine similarity
  text_emb_norm = text_emb / np.linalg.norm(text_emb)
  sim = np.dot(retrieval_v, text_emb_norm)

  # Sort by highest similarity
  sorted_idx = np.argsort(-sim)
  if exclude_id is not None:
    sorted_idx_mask = retrieval_k[sorted_idx] != exclude_id
    sorted_idx = sorted_idx[sorted_idx_mask]

  # Get stats
  sorted_idx = sorted_idx[:retrieval_top_k]
  retrieval_data = [dataset[int(d_id)] for d_id in retrieval_k[sorted_idx]]
  retrieval_stats_sim = sim[sorted_idx]

  return retrieval_data, retrieval_stats_sim


def attribute(
    text,
    forward,
    params,
    alphabet,
    vocab_char_size,
    vision_img=None,
    vision_output_size=(224, 224),
) -> AttributionResults:
  """Computes predicted date and geographical region."""

  (text, _, _, text_char, text_len, padding, _) = _prepare_text(text, alphabet)

  if vision_img is not None:
    vision_img = process_img(vision_img, output_size=vision_output_size)
    vision_img = np.array(vision_img)[None, ..., None]
    vision_img = vision_img / 127.5 - 1.0
    vision_available = np.ones((1,))
  else:
    vision_img = np.zeros((1, vision_output_size[0], vision_output_size[1], 1))
    vision_available = np.zeros((1,))

  rng = jax.random.PRNGKey(SEED)
  date_logits, subregion_logits, _, _, _ = forward(
      params,
      text_char=text_char,
      vision_img=vision_img,
      vision_available=vision_available,
      rngs={'dropout': rng},
      is_training=False,
  )

  # Generate subregion predictions:
  subregion_logits = np.array(subregion_logits)
  subregion_pred_probs = eval_util.softmax(subregion_logits[0]).tolist()
  location_predictions = [
      LocationPrediction(location_id=id, score=prob)
      for id, prob in enumerate(subregion_pred_probs)
  ]
  location_predictions.sort(key=lambda loc: loc.score, reverse=True)

  # Generate date predictions:
  date_pred_probs = eval_util.softmax(date_logits[0])

  # Gradients for saliency maps
  date_saliency, subregion_saliency = (
      eval_util.compute_attribution_saliency_maps(
          text_char,
          text_len,
          padding,
          forward,
          params,
          alphabet,
          vocab_char_size,
      )
  )

  # Skip start of sequence symbol (first char) for text and saliency maps:
  return AttributionResults(
      input_text=text,
      locations=location_predictions,
      year_scores=date_pred_probs.tolist(),
      date_saliency=date_saliency.tolist()[1:],
      location_saliency=subregion_saliency.tolist()[1:],
  )


def restore(
    text,
    forward,
    params,
    alphabet,
    vocab_char_size,
    beam_width=RESTORATION_BEAM_WIDTH,
    temperature=RESTORATION_TEMPERATURE,
    unk_restoration_max_len=UNK_RESTORATION_MAX_LEN,
    a_penalty=A_PENALTY,
) -> RestorationResults:
  """Performs search to compute text restoration. Slower, runs synchronously."""

  if (
      ALPHABET_MISSING_RESTORE not in text
      and ALPHABET_MISSING_UNK_RESTORE not in text
  ):
    raise ValueError('At least one character must be missing.')

  count_unk = text.count(ALPHABET_MISSING_UNK_RESTORE)
  (text, _, text_padded, _, text_len, _, restore_mask_idx) = _prepare_text(
      text, alphabet
  )

  # Check maximum length of unknown restoration
  if ALPHABET_MISSING_UNK_RESTORE in text:
    if unk_restoration_max_len < 1:
      # Must be at least 1
      raise ValueError('unk_restoration_max_len must be at least 1.')
    elif unk_restoration_max_len > UNK_RESTORATION_MAX_LEN:
      # Clip to the default maximum length
      raise ValueError(
          'unk_restoration_max_len=%d > maximum value %d.'
          % (
              unk_restoration_max_len,
              UNK_RESTORATION_MAX_LEN,
          )
      )

    # Define maximum restoration length
    max_len = min(
        text_len[0] - count_unk + unk_restoration_max_len,
        TEXT_LEN,
    )
  else:
    max_len = text_len[0]

  beam_result = eval_util.beam_search_batch(
      forward,
      params,
      alphabet,
      text_padded,
      restore_mask_idx,
      max_len=max_len,
      beam_width=beam_width,
      temperature=temperature,
      sequential_decoding=False,
      a_penalty=a_penalty,
  )

  # For visualization purposes, we strip out the SOS and padding, and adjust
  # restored_indices accordingly
  predictions = [
      Restoration(
          text=beam_entry.text_pred[1:].rstrip(alphabet.pad),
          restored=[i - 1 for i in beam_entry.mask_idx],
          score=math.exp(beam_entry.pred_logprob),
      )
      for beam_entry in beam_result
  ]
  missing_indices = [i - 1 for i in restore_mask_idx]

  # Sequence of saliency maps for the top prediction's trajectory:
  saliency_char_steps = []
  if beam_result:
    # Use the trajectory from the top beam result for saliency
    top_beam_entry = beam_result[0]
    saliency_generator = eval_util.sequential_restoration_saliency(
        top_beam_entry.text_history,  # Pass the history from the top beam
        forward,
        params,
        alphabet,
        vocab_char_size,
    )
    saliency_char_steps = [
        RestorationCharSaliency(
            step.text[1:].rstrip(alphabet.pad),
            int(step.pred_char_pos) - 1,
            step.saliency_map.tolist(),
        )
        for step in saliency_generator
    ]

  return RestorationResults(
      input_text=text,
      # Handle case where predictions might be empty, though beam_search_batch
      # is expected to return at least one result if successful.
      top_prediction=predictions[0].text if predictions else '',
      missing=missing_indices,
      predictions=predictions,
      prediction_saliency=saliency_char_steps,
  )


def contextualize(
    text,
    dataset,
    retrieval,
    forward,
    params,
    alphabet,
    region_map,
    include_test=True,
    top_k=20,
) -> ContextualizationResults:
  """Performs search to compute text restoration. Slower, runs synchronously."""

  text_emb = _generate_text_emb(params, forward, alphabet, text, emb_mode='avg')

  context_data, context_score = _get_relevant_texts(
      dataset,
      retrieval,
      text_emb,
      normalize=True,
      include_test=include_test,
      retrieval_top_k=top_k,
  )

  ids = []
  ids_alt = []
  text = []
  location_ids = []
  date_min = []
  date_max = []
  partner_link = []
  score = []
  for d, s in zip(context_data, context_score):
    ids.append(d.get('record_number', d.get('id')))
    ids_alt_dict = {k: str(v) for k, v in d['ids_alt'].items()}
    ids_alt.append(ids_alt_dict)
    text.append(d['text'])
    score.append(float(s))

    if 'region_sub' in d and d['region_sub'] is not None:
      region_sub_name = region_names.region_name_filter(d['region_sub'])
      location_ids.append(region_map['names_inv'][region_sub_name])
    else:
      location_ids.append(None)

    if 'date_min' in d and d['date_min'] is not None:
      date_min.append(int(d['date_min']))
    else:
      date_min.append(None)

    if 'date_max' in d and d['date_max'] is not None:
      date_max.append(int(d['date_max']))
    else:
      date_max.append(None)

    if 'partner_link' in d:
      partner_link.append(d['partner_link'])
    else:
      partner_link.append(None)

  return ContextualizationResults(
      ids=ids,
      ids_alt=ids_alt,
      text=text,
      location_ids=location_ids,
      date_min=date_min,
      date_max=date_max,
      partner_link=partner_link,
      score=score,
  )


def load_dataset(path):
  """Loads a dataset json."""
  with open(path, 'r') as f:
    json_data = json.load(f)
  dataset = {}
  for d in json_data:
    d['id'] = int(d['id'])
    dataset[d['id']] = d
  return dataset


def load_retrieval(path):
  """Loads and preprocesses pre-computed embeddings for retrieval.

  This function loads a pickle file containing embeddings, splits them into
  training, testing, and "all" sets, normalizes them, and calculates
  L2-normalized versions. The embeddings are assumed to be stored as a
  dictionary where keys are integer IDs and values are dictionaries containing
  at least an 'avg' key with the embedding vector.

  Args:
    path: Path to the pickle file containing the embeddings.

  Returns:
    A dictionary containing the processed embeddings and related information.
    The dictionary has the following keys:
      - 'emb_k': An array of embedding keys for training (excluding those
        ending in 3 or 4).
      - 'emb_k_all': An array of all embedding keys (integer IDs).
      - 'emb_v': An array of embedding vectors for training.
      - 'emb_v_all': An array of all embedding vectors.
      - 'emb_v_mean': The mean of the training embeddings.
      - 'emb_v_std': The standard deviation of the training embeddings.
      - 'emb_v_normed': L2-normalized training embeddings.
      - 'emb_v_all_normed': L2-normalized "all" embeddings.
  """
  # Load embeddings
  retrieval = {}
  with open(path, 'rb') as f:
    embed = pickle.load(f)
  retrieval['emb_k_all'] = np.array(list(embed.keys()), dtype=np.int32)

  # Embeddings for training and test
  retrieval['emb_k'] = np.array(
      [k for k in retrieval['emb_k_all'] if k % 10 not in [3, 4]],
      dtype=np.int32,
  )
  emb_v = np.array([embed[k]['avg'] for k in retrieval['emb_k']])
  emb_v_all = np.array([embed[k]['avg'] for k in retrieval['emb_k_all']])

  # Normalize embeddings
  retrieval['emb_v_mean'] = np.mean(emb_v, axis=0)
  retrieval['emb_v_std'] = np.std(emb_v, axis=0)
  emb_v_normed = (emb_v - retrieval['emb_v_mean']) / retrieval['emb_v_std']
  emb_v_all_normed = (emb_v_all - retrieval['emb_v_mean']) / retrieval[
      'emb_v_std'
  ]

  retrieval['emb_v_normed'] = emb_v_normed / np.linalg.norm(
      emb_v_normed, axis=1, keepdims=True
  )
  retrieval['emb_v_all_normed'] = emb_v_all_normed / np.linalg.norm(
      emb_v_all_normed, axis=1, keepdims=True
  )
  return retrieval
