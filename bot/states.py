"""FSM states for the customer flow."""

from aiogram.fsm.state import State, StatesGroup


class OrderFlow(StatesGroup):
    quantity = State()
    name = State()
    phone = State()
    address = State()
    payment = State()
    confirm = State()


class TrackFlow(StatesGroup):
    number = State()
