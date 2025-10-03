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
"""Subregion mapping used to train the model.

The subregion IDs originate from the I.PHI generator and may be subject to
change in future versions of the PHI dataset.
"""


def region_name_filter(region_name):
  """Region names filter."""
  filter_map = {
      'Bruttium et Lucania': 'Bruttii et Lucania',  # Latin
      'Caria, Rhodian Peraia': 'Caria',  # Greek
      'Cilicia and Isauria': 'Cilicia',  # Greek
      'Creta': 'Crete',  # Latin
      'Cyrenaïca': 'Cyrenaica',  # Greek
      'Cyrene': 'Cyrenaica',  # Latin
      'Epeiros, Illyria, and Dalmatia': 'Epirus',  # Greek
      'Hispania and Lusitania': 'Hispania citerior and Lusitania',  # Greek
      'Hispania citerior': 'Hispania citerior',  # Latin
      'Lycia et Pamphylia': 'Lycia',  # Latin
      'Moesia Superior': 'Moesia superior',  # Greek
      'Mysia [Kaïkos], Pergamon': 'Mysia Kaikos, Pergamon',  # Greek
      'Mysia [Upper Kaïkos] / Lydia': 'Mysia Upper Kaikos / Lydia',  # Greek
      'Raetia': 'Raetia, Noricum, and Pannonia',  # Latin
      'Sabina et Samnium': 'Samnium',  # Latin
      'Sicilia, Melita': 'Sicily, Sardinia',  # Latin
      'Sicily, Sardinia, and neighboring Islands': 'Sicily, Sardinia',  # Greek
      'Syria': 'Syria and Phoenicia',  # Latin
      'Thrace and Moesia Inferior': 'Thrace',  # Greek
      'Thracia': 'Thrace',  # Latin
  }
  # Return if None
  if region_name is None:
    return None

  # Check if region in the map
  region_name = region_name.strip()
  if region_name in filter_map:
    region_name = filter_map[region_name]

  # Remove parentheses
  if '(' in region_name:
    region_name = region_name.split('(')[0].strip()

  return region_name
