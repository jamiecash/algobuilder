"""
URL Path converters
"""
import ast
from datetime import datetime


class DatetimeConverter:
    # TODO check if these need to include timezone %z or %Z once dates on form are completed
    regex = '[12][0-9]{3}-[01][0-2]-[0-3][0-9]T[0-2][0-9]:[0-6][0-9]:[0-6][0-9]'
    __format = '%Y-%m-%dT%H:%M:%S'

    def to_python(self, value: str):
        return datetime.strptime(value, self.__format).date()

    def to_url(self, value: datetime):
        return value.strftime(self.__format)


class ListOfStringsConverter:
    regex = r"\[('[A-Za-z0-9]*'\,)*'[A-Za-z0-9]*'\]"

    def to_python(self, value: str):
        return ast.literal_eval(value)

    def to_url(self, value: datetime):
        return str(value)
