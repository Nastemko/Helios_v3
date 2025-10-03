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
"""Alphabet classes."""
import re
import numpy as np


class Alphabet(object):
  """Generic alphabet class."""

  def __init__(
      self,
      alphabet,
      numerals='0',
      punctuation='.',
      space=' ',
      missing='-',
      missing_unk='_',
      pad='#',
      unk='^',
      sos='<',
      sog='[',
      eog=']',
  ):
    self.alphabet = list(alphabet)  # alph
    self.numerals = list(numerals)  # num
    self.punctuation = list(punctuation)  # punt
    self.space = space  # spacing
    self.missing = missing  # missing char
    self.missing_unk = missing_unk  # missing unknown length
    self.pad = pad  # padding (spaces to right of string)
    self.unk = unk  # unknown char
    self.sos = sos  # start of sentence
    self.sog = sog  # start of guess
    self.eog = eog  # end of guess

    # Define vocab mapping
    self.idx2char = np.array(
        [
            self.pad,
            self.sos,
            self.unk,
            self.space,
            self.missing,
            self.missing_unk,
        ]
        + self.alphabet
        + self.numerals
        + self.punctuation
    )
    self.char2idx = {self.idx2char[i]: i for i in range(len(self.idx2char))}
    # Define special character indices
    self.pad_idx = self.char2idx[pad]
    self.sos_idx = self.char2idx[sos]
    self.unk_idx = self.char2idx[unk]
    self.alphabet_start_idx = self.char2idx[self.alphabet[0]]
    self.alphabet_end_idx = self.char2idx[self.numerals[-1]]

  def filter(self, t):
    return t

  def size_char(self):
    return len(self.idx2char)


class GreekAlphabet(Alphabet):
  """Greek alphabet class."""

  def __init__(self):
    greek_alphabet = 'αβγδεζηθικλμνξοπρςστυφχψωϙϛ'
    super().__init__(alphabet=greek_alphabet)
    self.tonos_to_oxia = {
        # tonos  : #oxia
        '\u0386': '\u1FBB',  # capital letter alpha
        '\u0388': '\u1FC9',  # capital letter epsilon
        '\u0389': '\u1FCB',  # capital letter eta
        '\u038C': '\u1FF9',  # capital letter omicron
        '\u038A': '\u1FDB',  # capital letter iota
        '\u038E': '\u1FF9',  # capital letter upsilon
        '\u038F': '\u1FFB',  # capital letter omega
        '\u03AC': '\u1F71',  # small letter alpha
        '\u03AD': '\u1F73',  # small letter epsilon
        '\u03AE': '\u1F75',  # small letter eta
        '\u0390': '\u1FD3',  # small letter iota with dialytika and tonos/oxia
        '\u03AF': '\u1F77',  # small letter iota
        '\u03CC': '\u1F79',  # small letter omicron
        '\u03B0': '\u1FE3',
        # small letter upsilon with dialytika and tonos/oxia
        '\u03CD': '\u1F7B',  # small letter upsilon
        '\u03CE': '\u1F7D',  # small letter omega
    }
    self.oxia_to_tonos = {v: k for k, v in self.tonos_to_oxia.items()}

  def filter(self, t):  # override previous filter function
    # lowercase
    t = t.lower()
    # replace dot below
    t = t.replace('\u0323', '')
    # replace perispomeni
    t = t.replace('\u0342', '')
    t = t.replace('\u02C9', '')
    # replace ending sigma
    t = re.sub(r'([\w\[\]])σ(?![\[\]])(\b)', r'\1ς\2', t)
    # replace oxia with tonos
    for oxia, tonos in self.oxia_to_tonos.items():
      t = t.replace(oxia, tonos)
    # replace h
    h_patterns = {
        # input: #target
        'ε': 'ἑ',
        'ὲ': 'ἓ',
        'έ': 'ἕ',
        'α': 'ἁ',
        'ὰ': 'ἃ',
        'ά': 'ἅ',
        'ᾶ': 'ἇ',
        'ι': 'ἱ',
        'ὶ': 'ἳ',
        'ί': 'ἵ',
        'ῖ': 'ἷ',
        'ο': 'ὁ',
        'ό': 'ὅ',
        'ὸ': 'ὃ',
        'υ': 'ὑ',
        'ὺ': 'ὓ',
        'ύ': 'ὕ',
        'ῦ': 'ὗ',
        'ὴ': 'ἣ',
        'η': 'ἡ',
        'ή': 'ἥ',
        'ῆ': 'ἧ',
        'ὼ': 'ὣ',
        'ώ': 'ὥ',
        'ω': 'ὡ',
        'ῶ': 'ὧ',
    }
    # iterate by keys
    for h_in, h_tar in h_patterns.items():
      # look up and replace h[ and h]
      t = re.sub(r'ℎ(\[?){}'.format(h_in), r'\1{}'.format(h_tar), t)
      t = re.sub(r'ℎ(\]?){}'.format(h_in), r'{}\1'.format(h_tar), t)
    # any h left is an ἡ
    t = re.sub(r'(\[?)ℎ(\]?)', r'\1ἡ\2', t)
    return t


class LatinAlphabet(object):
  """Latin alphabet class."""

  def __init__(
      self,
      numerals='0',
      punctuation='.',
      space=' ',
      missing='-',
      missing_unk='_',
      pad='#',
      unk='^',
      sos='<',
      sog='[',
      eog=']',
      **kwargs
  ):
    del kwargs
    latin_alphabet = 'abcdefghiklmnopqrstuvxyz'
    self.alphabet = list(latin_alphabet)  # alph
    self.numerals = list(numerals)  # num
    self.punctuation = list(punctuation)  # punt
    self.space = space  # spacing
    self.missing = missing  # missing char
    self.missing_unk = missing_unk  # missing unknown length
    self.pad = pad  # padding (spaces to right of string)
    self.unk = unk  # unknown char
    self.sos = sos  # start of sentence
    self.sog = sog  # start of guess
    self.eog = eog  # end of guess

    # Define vocab mapping
    self.idx2char = np.array(
        [
            self.pad,
            self.sos,
            self.unk,
            self.space,
            self.missing,
            self.missing_unk,
        ]
        + self.alphabet
        + self.numerals
        + self.punctuation
    )
    self.char2idx = {self.idx2char[i]: i for i in range(len(self.idx2char))}

    # Define special character indices
    self.pad_idx = self.char2idx[pad]
    self.sos_idx = self.char2idx[sos]
    self.unk_idx = self.char2idx[unk]
    self.alphabet_start_idx = self.char2idx[self.alphabet[0]]
    self.alphabet_end_idx = self.char2idx[self.numerals[-1]]

  def filter(self, t):
    """Removes common punctuation marks from a string."""
    t = re.sub(r'[!,;?\·]', '', t)
    return t


class GreekLatinAlphabet(object):
  """Greek-Latin alphabet class."""

  def __init__(
      self,
      numerals='0',
      punctuation='!,.;?·',
      space=' ',
      missing='-',
      missing_unk='_',
      pad='#',
      unk='^',
      sos='<',
      sog='[',
      eog=']',
  ):
    latin_alphabet = 'abcdefghiklmnopqrstuvxyz'
    greek_alphabet = 'αβγδεζηθικλμνξοπρςστυφχψωϙϛ'
    self.alphabet = list(latin_alphabet + greek_alphabet)  # alph
    self.numerals = list(numerals)  # num
    self.punctuation = list(punctuation)  # punt
    self.space = space  # spacing
    self.missing = missing  # missing char
    self.missing_unk = missing_unk  # missing unknown length
    self.pad = pad  # padding (spaces to right of string)
    self.unk = unk  # unknown char
    self.sos = sos  # start of sentence
    self.sog = sog  # start of guess
    self.eog = eog  # end of guess

    # Define vocab mapping
    self.idx2char = np.array(
        [
            self.pad,
            self.sos,
            self.unk,
            self.space,
            self.missing,
            self.missing_unk,
        ]
        + self.alphabet
        + self.numerals
        + self.punctuation
    )
    self.char2idx = {self.idx2char[i]: i for i in range(len(self.idx2char))}
    # Define special character indices
    self.pad_idx = self.char2idx[pad]
    self.sos_idx = self.char2idx[sos]
    self.unk_idx = self.char2idx[unk]
    self.alphabet_start_idx = self.char2idx[self.alphabet[0]]
    self.alphabet_end_idx = self.char2idx[self.numerals[-1]]
