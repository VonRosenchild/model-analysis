# Copyright 2019 Google LLC
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
"""Metric types."""

from __future__ import absolute_import
from __future__ import division
# Standard __future__ imports
from __future__ import print_function

import apache_beam as beam
from tensorflow_model_analysis import types
from tensorflow_model_analysis.proto import metrics_for_slice_pb2
from typing import Any, Callable, Dict, List, Optional, Text, NamedTuple, Union

# LINT.IfChange


# A separate version from proto is used here because protos are not hashable and
# SerializeToString is not guaranteed to be stable between different binaries.
class SubKey(
    NamedTuple('SubKey', [('class_id', int), ('k', int), ('top_k', int)])):
  """A SubKey identifies a sub-types of metrics and plots.

  Only one of class_id, k, or top_k can be set at a time.

  Attributes:
    class_id: Used with multi-class metrics to identify a specific class ID.
    k: Used with multi-class metrics to identify the kth predicted value.
    top_k: Used with multi-class and ranking metrics to identify top-k predicted
      values.
  """

  def __new__(cls,
              class_id: Optional[int] = None,
              k: Optional[int] = None,
              top_k: Optional[int] = None):
    if sum([0 if v is None else 1 for v in (class_id, k, top_k)]) > 1:
      raise ValueError('only one of class_id, k, or top_k should be used: '
                       'class_id={}, k={}, top_k={}'.format(class_id, k, top_k))
    if k is not None and k < 1:
      raise ValueError('attempt to create metric with k < 1: k={}'.format(k))
    if top_k is not None and top_k < 1:
      raise ValueError(
          'attempt to create metric with top_k < 1: top_k={}'.format(top_k))
    return super(SubKey, cls).__new__(cls, class_id, k, top_k)

  def to_proto(self) -> metrics_for_slice_pb2.SubKey:
    """Converts key to proto."""
    sub_key = metrics_for_slice_pb2.SubKey()
    if self.class_id is not None:
      sub_key.class_id.value = self.class_id
    if self.k is not None:
      sub_key.k.value = self.k
    if self.top_k is not None:
      sub_key.top_k.value = self.top_k
    return sub_key


# A separate version from proto is used here because protos are not hashable and
# SerializeToString is not guaranteed to be stable between different binaries.
class MetricKey(
    NamedTuple('MetricKey', [('name', Text), ('model_name', Text),
                             ('output_name', Text), ('sub_key', SubKey)])):
  """A MetricKey uniquely identifies a metric.

  Attributes:
    name: Metric name. Names starting with '_' are private and will be filtered
      from the final results.
    model_name: Optional model name (if multi-model evaluation).
    output_name: Optional output name (if multi-output model type).
    sub_key: Optional sub key.
  """

  def __new__(cls,
              name: Text,
              model_name: Text = '',
              output_name: Text = '',
              sub_key: Optional[SubKey] = None):
    return super(MetricKey, cls).__new__(cls, name, model_name, output_name,
                                         sub_key)

  def to_proto(self) -> metrics_for_slice_pb2.MetricKey:
    """Converts key to proto."""
    metric_key = metrics_for_slice_pb2.MetricKey()
    if self.name:
      metric_key.name = self.name
    if self.model_name:
      metric_key.model_name = self.model_name
    if self.output_name:
      metric_key.output_name = self.output_name
    if self.sub_key:
      metric_key.sub_key.CopyFrom(self.sub_key.to_proto())
    return metric_key


# A separate version from proto is used here because protos are not hashable and
# SerializeToString is not guaranteed to be stable between different binaries.
# In addition internally PlotKey is a subclass of MetricKey as each plot is
# stored separately.
class PlotKey(MetricKey):
  """A PlotKey is a metric key that uniquely identifies a plot."""

  def to_proto(self) -> metrics_for_slice_pb2.PlotKey:
    """Converts key to proto."""
    plot_key = metrics_for_slice_pb2.PlotKey()
    if self.name:
      raise ValueError('plot values must be combined into a single proto and'
                       'stored under a plot key without a name')
    if self.model_name:
      plot_key.model_name = self.model_name
    if self.output_name:
      plot_key.output_name = self.output_name
    if self.sub_key:
      plot_key.sub_key.CopyFrom(self.sub_key.to_proto())
    return plot_key


# LINT.ThenChange(../proto/metrics_for_slice.proto)


class MetricComputation(
    NamedTuple('MetricComputation', [('keys', List[MetricKey]),
                                     ('preprocessor', beam.DoFn),
                                     ('combiner', beam.CombineFn)])):
  """MetricComputation represents one or more metric computations.

  The preprocessor is called with a PCollection of extracts to compute the
  initial combiner input state which is then passed to the combiner. This needs
  to be done in two steps because slicing happens between the call to the
  preprocessor and the combiner and this state may end up in multiple slices so
  we want the representation to be as efficient as possible. If the preprocessor
  is None, then StandardMetricInputs will be passed.

  Attributes:
    keys: List of metric keys associated with computation.
    preprocessor: Takes a extracts as input (which typically will contain
      labels, predictions, example weights, and optionally features) and should
      return the initial state that the combiner will use as input. The output
      of a processor should only contain information needed by the combiner.
    combiner: Takes preprocessor output as input and outputs a tuple: (slice,
      metric results). The metric results should be a dict from MetricKey to
      value (float, int, distribution, ...).
  """

  def __new__(cls, keys: List[MetricKey], preprocessor: beam.DoFn,
              combiner: beam.CombineFn):
    return super(MetricComputation, cls).__new__(cls, keys, preprocessor,
                                                 combiner)


class DerivedMetricComputation(
    NamedTuple(
        'DerivedMetricComputation',
        [('keys', List[MetricKey]),
         ('result', Callable)]  # Dict[MetricKey,Any] -> Dict[MetricKey,Any]
    )):
  """DerivedMetricComputation derives its result from other computations.

  Attributes:
    keys: List of metric keys associated with derived computation.
    result: Function (called per slice) to compute the result using the results
      of other metric computations.
  """

  def __new__(cls, keys: List[MetricKey],
              result: Callable[[Dict[MetricKey, Any]], Dict[MetricKey, Any]]):
    return super(DerivedMetricComputation, cls).__new__(cls, keys, result)


# MetricComputations is a list of derived and non-derived computations used to
# calculate one or more metric values. Derived metrics should come after the
# computations they depend on in the list.
MetricComputations = List[Union[MetricComputation, DerivedMetricComputation]]


class Metric(object):
  """Metric wraps a set of metric computations.

  This class exists to provide similarity between tfma.metrics.Metric and
  tf.keras.metics.Metric.

  Calling computations creates the metric computations. The parameters passed to
  __init__ will be combined with the parameters passed to the computations
  method. This allows some of the parameters (e.g. model_name, output_name,
  sub_key) to be set at the time the computations are created instead of when
  the metric is defined.
  """

  def __init__(self, create_computations_fn: Callable[..., MetricComputations],
               **kwargs):
    """Initializes metric.

    Args:
      create_computations_fn: Function to create the metrics computations (e.g.
        mean_label, etc). This function should take the args passed to __init__
        as as input along with model_name, output_name, and sub_key (even if not
        applicable).
      **kwargs: Any additional kwargs to pass to create_computations_fn. These
        should only contain primitive types or lists/dicts of primitive types.
    """
    self.create_computations_fn = create_computations_fn
    self.kwargs = kwargs

  def computations(self,
                   model_name: Optional[Text] = None,
                   output_name: Optional[Text] = None,
                   sub_key: Optional[SubKey] = None):
    return self.create_computations_fn(
        model_name=model_name,
        output_name=output_name,
        sub_key=sub_key,
        **self.kwargs)


class StandardMetricInputs(
    NamedTuple('StandardMetricInputs',
               [('label', types.TensorValueMaybeDict),
                ('prediction', Union[types.TensorValueMaybeDict,
                                     Dict[Text, types.TensorValueMaybeDict]]),
                ('example_weight', types.TensorValueMaybeDict)])):
  """Standard inputs used by most metric computations.

  All values are copies of the respective values that were stored in the
  extracts. These may be multi-level dicts if a multi-model evalations was run
  or the models are multi-output models.

  Attributes:
    label: Copy of LABELS_KEY extract.
    prediction: Copy of PREDICTIONS_KEY extract.
    example_weight: Copy of EXAMPLE_WEIGHT_KEY extract.
  """

  def __new__(cls, label: types.TensorValueMaybeDict,
              prediction: Union[types.TensorValueMaybeDict,
                                Dict[Text, types.TensorValueMaybeDict]],
              example_weight: types.TensorValueMaybeDict):
    return super(StandardMetricInputs, cls).__new__(cls, label, prediction,
                                                    example_weight)
