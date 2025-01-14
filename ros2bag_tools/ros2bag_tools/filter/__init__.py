# Copyright 2021 AIT Austrian Institute of Technology GmbH
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from enum import Enum
from typing import Tuple, Union, List, Sequence
import argparse
from rosbag2_py import TopicMetadata, BagMetadata, StorageFilter
from rclpy.exceptions import InvalidTopicNameException
from rclpy.validate_topic_name import validate_topic_name
from rclpy.serialization import deserialize_message, serialize_message
from rosidl_runtime_py.utilities import get_message
from ros2cli.plugin_system import PLUGIN_SYSTEM_VERSION, satisfies_version
from logging import Logger, getLogger


class FilterResult(Enum):
    DROP_MESSAGE = 1
    STOP_CURRENT_BAG = 2


BagMessageTuple = Tuple[str, bytes, int]


class FilterExtension:
    """
    The extension point for bag filter verb extensions.

    The following properties must be defined:
    * `NAME`

    The following methods can be defined:
    * `add_arguments`
    * `set_args`
    * `get_storage_filter`
    * `output_size_factor`
    * `filter_topic`
    * `filter_msg`
    """

    EXTENSION_POINT_VERSION = '0.1'

    def __init__(self, logger: Union[Logger, str, None] = None):
        super(FilterExtension, self).__init__()
        satisfies_version(PLUGIN_SYSTEM_VERSION, '^0.1')

        if isinstance(logger, str):
            self._logger = getLogger(logger)
        elif logger is None:
            self._logger = getLogger(__name__)
        else:
            self._logger = logger

    def set_logger(self, logger: Logger):
        if logger is None:
            raise ValueError("Setting a {logger} is not permitted")
        self._logger = logger

    def add_arguments(self, _args):
        pass

    def set_args(self, _metadata: Sequence[BagMetadata], _args):
        pass

    def get_storage_filter(self) -> StorageFilter:
        return None

    def output_size_factor(self, _metadata: BagMetadata):
        """Estimate multiple of input messages this filter will output."""
        return 1.0

    def filter_topic(self, topic: TopicMetadata) -> Union[TopicMetadata, List[TopicMetadata]]:
        return topic

    def filter_msg(self, msg: BagMessageTuple) -> Union[FilterResult, BagMessageTuple, List]:
        return msg

    def flush(self) -> Union[FilterResult, BagMessageTuple, List]:
        """
        Flush remaining contents or logs.

        Output any remaining messages or logs. filter_msg may still be called
        as other filters in the front of the chain may have produced some messages to filter.

        For single filters it makes no sense to return a FilterResult here.
        This will only we be valid for filters like the CompositeFilters.
        """
        return []


def TopicNameArg(value):
    try:
        validate_topic_name(value)
    except InvalidTopicNameException as e:
        raise argparse.ArgumentTypeError(str(e))
    return value


class TypeAwareTopicFilter(FilterExtension):

    def __init__(self, *args, **kwargs):
        super(TypeAwareTopicFilter, self).__init__(*args, **kwargs)
        self._message_type = None
        self._topic = None

    def add_arguments(self, parser):
        parser.add_argument(
            '-t', '--topic', help='target topic name', required=True, type=TopicNameArg)

    @property
    def topic(self):
        return self._topic

    def set_args(self, _metadata, args):
        self._topic = args.topic

    def filter_topic(self, topic_metadata):
        if topic_metadata.name == self._topic:
            topic_type_name = topic_metadata.type
            try:
                self._message_type = get_message(topic_type_name)
            except (AttributeError, ModuleNotFoundError, ValueError):
                raise RuntimeError(
                    f"failed to load message type '{topic_type_name}'")
        return topic_metadata

    def filter_msg(self, msg):
        (topic, data, t) = msg
        if topic == self._topic:
            msg = deserialize_message(data, self._message_type)
            result = self.filter_typed_msg((topic, msg, t))
            if isinstance(result, FilterResult):
                return result
            (topic, msg, t) = result
            return (topic, serialize_message(msg), t)
        return msg

    def filter_typed_msg(self, _msg):
        raise NotImplementedError()
