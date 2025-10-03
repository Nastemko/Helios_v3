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
"""Example for running inference. See also colab."""

import pickle  # pylint: disable=pickle-use

from absl import app
from absl import flags
import jax
from predictingthepast.eval import inference
from predictingthepast.models.model import Model
from predictingthepast.util import alphabet as util_alphabet

FLAGS = flags.FLAGS

flags.DEFINE_string(
    'input',
    '',
    'Text to directly pass to the model. Only one of --input and '
    '--input_file can be specified.',
)
flags.DEFINE_string(
    'input_file',
    '',
    'File containing text to pass to the model. Only one of '
    '--input and --input_file can be specified.',
)
flags.DEFINE_string(
    'checkpoint_path', 'checkpoint.pkl', 'Path to model checkpoint pickle.'
)
flags.DEFINE_string('dataset_path', 'dataset.json', 'Path to dataset json.')
flags.DEFINE_string(
    'retrieval_path', 'retrieval.pkl', 'Path to retrieval pickle.'
)
flags.DEFINE_enum(
    'language',
    'latin',
    ['greek', 'latin'],
    'Language of the model (latin/greek).',
)
flags.DEFINE_string('attribute_json', '', 'Path to save attribution JSON to.')
flags.DEFINE_string('restore_json', '', 'Path to save restoration JSON to.')
flags.DEFINE_string(
    'contextualize_json', '', 'Path to save contextualize JSON to.'
)
# Restoration flags:
flags.DEFINE_integer('beam_width', 100, '')
flags.DEFINE_integer('max_restoration_len', 15, '')
flags.DEFINE_float('restoration_temperature', 1.0, '')


def load_checkpoint(path, language):
  """Loads a checkpoint pickle.

  Args:
    path: path to checkpoint pickle
    language: language of the model (latin/greek)

  Returns:
    a model config dictionary (arguments to the model's constructor), a dict of
    dicts containing region mapping information, a GreekAlphabet instance with
    indices and words populated from the checkpoint, a dict of Jax arrays
    `params`, and a `forward` function.
  """

  # Pickled checkpoint dict containing params and various config:
  with open(path, 'rb') as f:
    checkpoint = pickle.load(f)

  # We reconstruct the model using the same arguments as during training, which
  # are saved as a dict in the "model_config" key, and construct a `forward`
  # function of the form required by attribute() and restore().
  params = jax.device_put(checkpoint['params'])
  model = Model(**checkpoint['model_config'])
  forward = model.apply

  # Contains the mapping between region IDs and names:
  region_map = checkpoint['region_map']

  # Use vocabulary mapping from the checkpoint, the rest of the values in the
  # class are fixed and constant e.g. the padding symbol
  if language == 'latin':
    alphabet = util_alphabet.LatinAlphabet()
  elif language == 'greek':
    alphabet = util_alphabet.GreekAlphabet()
  else:
    raise ValueError(f'Unknown language: {language}')

  return checkpoint['model_config'], region_map, alphabet, params, forward


def main(argv):
  if len(argv) > 1:
    raise app.UsageError('Too many command-line arguments.')

  if FLAGS.input and not FLAGS.input_file:
    input_text = FLAGS.input
  elif not FLAGS.input and FLAGS.input_file:
    with open(FLAGS.input_file, 'r', encoding='utf8') as f:
      input_text = f.read()
  else:
    raise app.UsageError('Specify exactly one of --input and --input_file.')

  if not 50 <= len(input_text) <= 750:
    raise app.UsageError(
        'Text should be between 50 and 750 chars long, but the input was '
        f'{len(input_text)} characters'
    )

  # Load the checkpoint pickle and extract from it the pieces needed for calling
  # the attribute() and restore() functions:
  (model_config, region_map, alphabet, params, forward) = load_checkpoint(
      FLAGS.checkpoint_path, FLAGS.language
  )
  vocab_char_size = model_config['vocab_char_size']

  # Attribution
  attribution = inference.attribute(
      input_text,
      forward=forward,
      params=params,
      alphabet=alphabet,
      vocab_char_size=vocab_char_size,
  )
  if FLAGS.attribute_json:
    with open(FLAGS.attribute_json, 'w') as f:
      f.write(attribution.json(indent=2))
  else:
    print('Attribution:', attribution.json())

  # Restoration
  restoration = inference.restore(
      input_text,
      forward=forward,
      params=params,
      alphabet=alphabet,
      vocab_char_size=vocab_char_size,
      beam_width=FLAGS.beam_width,
      temperature=FLAGS.restoration_temperature,
      unk_restoration_max_len=FLAGS.max_restoration_len,
  )
  if FLAGS.restore_json:
    with open(FLAGS.restore_json, 'w') as f:
      f.write(restoration.json(indent=2))
  else:
    print('Restoration:', restoration.json())

  # Contextualization
  dataset = inference.load_dataset(FLAGS.dataset_path)
  retrieval = inference.load_retrieval(FLAGS.retrieval_path)
  contextualization = inference.contextualize(
      input_text, dataset, retrieval, forward, params, alphabet, region_map
  )
  if FLAGS.contextualize_json:
    with open(FLAGS.contextualize_json, 'w') as f:
      f.write(contextualization.json(indent=2))
  else:
    print('Contextualization:', contextualization.json())


if __name__ == '__main__':
  app.run(main)
