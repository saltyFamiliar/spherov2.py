import functools
import threading
import time
from collections import OrderedDict, defaultdict
from concurrent import futures
from functools import partial
from queue import SimpleQueue
from typing import NamedTuple, Callable

from spherov2.controls.v2 import Packet as PacketV2
from spherov2.types import ToyType


class ToySensor(NamedTuple):
    bit: int
    min_value: float
    max_value: float
    modifier: Callable[[float], float] = None


class Toy:
    """Base class for BOLT and Mini robots using V2 protocol"""
    toy_type = ToyType('Robot', None, 'Sphero', .06)
    sensors = OrderedDict()
    extended_sensors = OrderedDict()

    # V2 Protocol Configuration
    _send_uuid = '00010002-574f-4f20-5370-6865726f2121'
    _response_uuid = '00010002-574f-4f20-5370-6865726f2121'
    _handshake = []
    _packet = PacketV2
    _require_target = False

    def __init__(self, toy, adapter_cls):
        self.address = toy.address
        self.name = toy.name

        self.__adapter = None
        self.__adapter_cls = adapter_cls
        self._packet_manager = self._packet.Manager()
        self.__decoder = self._packet.Collector(self.__new_packet)
        self.__waiting = defaultdict(SimpleQueue)
        self.__listeners = defaultdict(dict)
        self._sensor_controller = None

        self.__thread = None
        self.__packet_queue = SimpleQueue()

    def __repr__(self):
        return f'{self.name} ({self.address})'

    def __enter__(self):
        if self.__adapter is not None:
            raise RuntimeError('Toy already in context manager')
        self.__adapter = self.__adapter_cls(self.address)
        self.__thread = threading.Thread(target=self.__process_packet)
        try:
            for uuid, data in self._handshake:
                self.__adapter.write(uuid, data)
            self.__adapter.set_callback(self._response_uuid, self.__api_read)
            self.__thread.start()
        except:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *args):
        self.__adapter.close()
        self.__adapter = None
        if self.__thread.is_alive():
            self.__packet_queue.put(None)
            self.__thread.join()
        self.__packet_queue = SimpleQueue()

    def __process_packet(self):
        while self.__adapter is not None:
            payload = self.__packet_queue.get()
            if payload is None:
                break
            while payload:
                self.__adapter.write(self._send_uuid, payload[:20])
                payload = payload[20:]
            time.sleep(self.toy_type.cmd_safe_interval)

    def _execute(self, packet):
        if self.__adapter is None:
            raise RuntimeError('Use toys in context manager')
        self.__packet_queue.put(packet.build())
        return self._wait_packet(packet.id)

    def _wait_packet(self, key, timeout=10.0, check_error=False):
        future = futures.Future()
        self.__waiting[key].put(future)
        packet = future.result(timeout)
        if check_error:
            packet.check_error()
        return packet

    def _add_listener(self, key, listener: Callable):
        self.__listeners[key[0]][listener] = partial(key[1], listener)

    def _remove_listener(self, key, listener: Callable):
        self.__listeners[key[0]].pop(listener)

    def __api_read(self, char, data):
        self.__decoder.add(data)

    def __new_packet(self, packet):
        key = packet.id
        queue = self.__waiting[key]
        while not queue.empty():
            queue.get().set_result(packet)
        for f in self.__listeners[key].values():
            threading.Thread(target=f, args=(packet,)).start()

    @classmethod
    def implements(cls, method, with_target=False):
        # Get the attribute directly from the class dict
        m = cls.__dict__.get(method.__name__, None)
        
        # Direct match
        if m is method:
            return with_target == cls._require_target
        
        # Check if it's a partialmethod
        if isinstance(m, functools.partialmethod):
            return m.func is method and (
                    ('proc' in m.keywords and not with_target) or with_target == cls._require_target)
        
        return False