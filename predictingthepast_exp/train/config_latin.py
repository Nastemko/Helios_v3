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
"""Config for a Aeneas experiment."""

from jaxline import base_config
from ml_collections import config_dict


def get_config():
  """Return config object for training."""

  config = base_config.get_base_config()

  # Experiment config.
  # Modify this to adapt to your custom distributed learning setup
  local_batch_size = 1
  num_devices = 1
  config.train_batch_size = local_batch_size * num_devices

  # Experiment config.
  config.macros = config_dict.ConfigDict(
      dict(
          context_char_max=768,
          date_max=800,
          date_min=-800,
          date_interval=10,
          date_bins=160,
          vision=False,
          prepend_sos=1,
      )
  )
  cm = config.macros  # Alias.

  config.experiment_kwargs = config_dict.ConfigDict(
      dict(
          config=dict(
              random_seed=4,
              random_mode_train=config.get_ref('random_mode_train'),
              random_mode_eval=config.get_ref('random_mode_eval'),
              optimizer=dict(
                  name='lamb',
                  kwargs=dict(
                      weight_decay=0.0,
                      b2=0.999,
                  ),
                  lr_schedule_kwargs=dict(
                      peak_value=3e-3,
                      init_value=1e-6,
                      warmup_steps=4_000,
                      decay_steps=1_000_000,
                      end_value=1e-5,
                  ),
                  clip_adaptive=False,
                  clip_level=0.0,
              ),
              training=dict(
                  batch_size=config.get_oneway_ref('train_batch_size')
              ),
              alphabet=dict(),
              dataset=dict(
                  vision=dict(
                      enabled=cm.get_ref('vision'),
                      path='data/img-20231005/',
                      output_size=(224, 224),
                      emb_dim=1280,
                      zoom_factor=2,
                      zoom_sampling_log=False,
                  ),
                  train_language=['latin'],
                  eval_language=['latin'],
                  latin_dataset_path='data/led.json',
                  greek_dataset_path='data/iphi.json',
                  greek_region_path='data/iphi-region-sub.txt',
                  latin_region_path='data/led-region-sub.txt',
                  context_char_min=25,
                  context_char_max=cm.get_ref('context_char_max'),
                  context_char_random=True,
                  char_use_guess=True,
                  char_mask_rate_min=0.0,
                  char_mask_rate_max=0.75,
                  span_mask_eval_len=10,
                  span_mask_ratio=0.15,
                  span_mask_geometric_p=0.1,
                  inject_missing_unk_p=0.25,
                  random_sentence_swap=0.25,
                  random_char_delete=0.0,
                  random_word_delete=0.2,
                  random_word_swap=0.0,
                  random_word_abbr=0.0,
                  punctuation_delete=True,
                  date_min=cm.get_ref('date_min'),
                  date_max=cm.get_ref('date_max'),
                  date_interval=cm.get_ref('date_interval'),
                  date_bins=cm.get_ref('date_bins'),
                  prepend_sos=cm.get_ref('prepend_sos'),
                  max_workers=None,
                  repeat_train=-1,
                  repeat_eval=10,
                  block_list=[],
                  allow_list=[],
              ),
              model=dict(
                  emb_word_disable=True,
                  emb_decoder_type='tied',
                  emb_init='normal',
                  emb_norm=True,
                  emb_dim=384,
                  qkv_dim=32,
                  mlp_dim=1536,
                  num_layers=16,
                  num_heads=8,
                  vocab_char_size=32,
                  output_regions=62,
                  output_date=cm.get_ref('date_bins'),
                  output_date_dist=True,
                  region_date_pooling='first',
                  use_output_mlp=True,
                  max_len=cm.get_ref('context_char_max'),
                  dropout_rate=0.1,
                  attention_dropout_rate=0.1,
                  use_bfloat16=False,
                  model_type='t5',
                  feature_combine_type='concat',
                  posemb_combine_type='concat',
                  activation_fn='gelu',
                  vision=cm.get_ref('vision'),
                  prepend_sos=cm.get_ref('prepend_sos'),
              ),
              loss=dict(
                  date=dict(
                      enabled=True,
                      weight=1.25,
                  ),
                  region=dict(
                      enabled=True,
                      weight=2.0,
                      label_smoothing=0.1,
                  ),
                  mask=dict(
                      enabled=True,
                      weight=3.0,
                      label_smoothing=0.05,
                  ),
                  nsp=dict(
                      enabled=False,
                      weight=1.0,
                  ),
                  unk=dict(
                      enabled=True,
                      weight=1.0,
                  ),
              ),
              evaluation=dict(
                  use_jit=True,
                  batch_size=1,
                  mode='valid',
                  store_model_log=False,
                  store_model_log_steps=100,
              ),
          ),
      )
  )

  # Training loop config.
  config.training_steps = 1_000_000
  config.log_train_data_interval = 10
  config.save_checkpoint_interval = 300
  config.best_model_eval_metric = 'score/eval'
  config.checkpoint_dir = '/tmp/predictingthepast_checkpoints'
  config.train_checkpoint_all_hosts = False

  # Prevents accidentally setting keys that aren't recognized (e.g. in tests).
  config.lock()

  return config
