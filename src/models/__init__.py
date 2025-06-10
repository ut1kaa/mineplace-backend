from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    """
   Base class for all models.

   Attributes:
       __abstract__ (bool): Whether the class is abstract.
       metadata (MetaData): The metadata for the models.
   """
    __abstract__ = True
    metadata = MetaData(naming_convention=convention)

    def __repr__(self) -> str:
        """
       Returns a string representation of the model.

       Returns:
           str: A string representation of the model.
       """
        columns = ", ".join(
            [f"{k}={repr(v)}" for k, v in self.__dict__.items() if not k.startswith("_")]
        )
        return f"<{self.__class__.__name__}({columns})>"

