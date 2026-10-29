"""A dnp3py outstation on 127.0.0.1:<port> for the end-to-end harness: a few inputs, outputs and a counter, every
binary control accepted (and reflected in the database), analog values below 1000 accepted."""
import asyncio
import sys

from dnp3.core.enums import ControlCode
from dnp3.core.flags import AnalogQuality, BinaryQuality, CounterQuality
from dnp3.database import (AnalogInputConfig, AnalogOutputConfig, BinaryInputConfig, BinaryOutputConfig, CounterConfig,
                           Database, EventClass)
from dnp3.outstation import CommandResult, DefaultCommandHandler, Outstation, OutstationConfig, OutstationTcpRunner


class Handler(DefaultCommandHandler):
    def __init__(self, database):
        self.database = database

    def _binary(self, index, code):
        if code in (ControlCode.LATCH_ON, ControlCode.LATCH_OFF):
            self.database.update_binary_output(index, code == ControlCode.LATCH_ON, quality=BinaryQuality.ONLINE)
        return CommandResult.success()

    def select_binary_output(self, index, code, count, on_time, off_time):
        return CommandResult.success()

    def operate_binary_output(self, index, code, count, on_time, off_time, select_sequence):
        return self._binary(index, code)

    def direct_operate_binary_output(self, index, code, count, on_time, off_time):
        return self._binary(index, code)

    def _analog(self, value):
        return CommandResult.success() if value < 1000 else CommandResult.out_of_range()

    def select_analog_output(self, index, value):
        return self._analog(value)

    def operate_analog_output(self, index, value, select_sequence):
        return self._analog(value)

    def direct_operate_analog_output(self, index, value):
        return self._analog(value)


def build_database() -> Database:
    db = Database()
    for i in (0, 1):
        db.add_binary_input(i, BinaryInputConfig(event_class=EventClass.CLASS_1))
        db.add_binary_output(i, BinaryOutputConfig())
        db.add_analog_output(i, AnalogOutputConfig())
        db.update_binary_output(i, False, quality=BinaryQuality.ONLINE)
    for i in (2, 3):
        db.add_analog_input(i, AnalogInputConfig(event_class=EventClass.CLASS_1))
    db.add_counter(5000, CounterConfig())
    db.update_binary_input(0, True, quality=BinaryQuality.ONLINE)
    db.update_binary_input(1, False, quality=BinaryQuality.ONLINE)
    db.update_analog_input(2, 2401, quality=AnalogQuality.ONLINE)
    db.update_analog_input(3, 50000, quality=AnalogQuality.ONLINE)
    db.update_analog_output(0, 10, quality=AnalogQuality.ONLINE)
    db.update_analog_output(1, 20, quality=AnalogQuality.ONLINE)
    db.update_counter(5000, 42, quality=CounterQuality.ONLINE)
    return db


async def main(port: int):
    database = build_database()
    outstation = Outstation(config=OutstationConfig(address=1, master_address=2), database=database, handler=Handler(database))
    await OutstationTcpRunner(outstation=outstation, host='127.0.0.1', port=port).run()


if __name__ == '__main__':
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 20000))
