#! /usr/bin/env python3

from sqlalchemy import Column, Date, DateTime, Float, Index, Integer, LargeBinary, Table
from sqlalchemy import Text, UniqueConstraint, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship as Relationship
import sqlalchemy.orm
import sqlalchemy

Base = declarative_base()
metadata = Base.metadata
engine = sqlalchemy.create_engine('sqlite:///ByDate/digikam4.db')
Session = sqlalchemy.orm.sessionmaker(bind=engine)
session = Session()

# class AlbumRoot(Base):
class Root(Base):
    __tablename__ = 'AlbumRoots'
    __table_args__ = (
        UniqueConstraint('identifier', 'specificPath'),
    )

    id = Column(Integer, primary_key=True)
    # label = Column(Text)
    name = Column('label', Text)
    status = Column(Integer, nullable=False)
    type = Column(Integer, nullable=False)
    identifier = Column(Text)
    # specificPath = Column(Text)
    path = Column('specificPath', Text)


class Album(Base):
    __tablename__ = 'Albums'
    __table_args__ = (
        UniqueConstraint('albumRoot', 'relativePath'),
    )

    id = Column(Integer, primary_key=True)
    # albumRoot = Column(Integer, nullable=False)
    root_id = Column('albumRoot', ForeignKey(Root.id), nullable=False)
    root = Relationship('Root', foreign_keys=[ root_id ], backref='albums')
    # relativePath = Column(Text, nullable=False)
    path = Column('relativePath', Text, nullable=False)
    date = Column(Date)
    caption = Column(Text)
    collection = Column(Text)
    icon = Column(Integer)


class Image(Base):
    __tablename__ = 'Images'
    __table_args__ = (
        UniqueConstraint('album', 'name'),
    )

    id = Column(Integer, primary_key=True)
    album = Column(Integer, index=True)
    name = Column(Text, nullable=False, index=True)
    status = Column(Integer, nullable=False)
    category = Column(Integer, nullable=False)
    # modificationDate = Column(DateTime)
    # modification_date = Column('modificationDate', DateTime)
    modification_date = Column('modificationDate', Text)
    # fileSize = Column(Integer)
    file_size = Column('fileSize', Integer)
    # uniqueHash = Column(Text, index=True)
    hash = Column('uniqueHash', Text, index=True)


class ImageInformation(Base):
    __tablename__ = 'ImageInformation'

    # imageid = Column(Integer, primary_key=True)
    image_id = Column('imageid', ForeignKey(Image.id), primary_key=True)
    image = Relationship('Image', foreign_keys = [ image_id ], backref='info')
    rating = Column(Integer)
    # creationDate = Column(DateTime, index=True)
    # creation_date = Column('creationDate', DateTime, index=True)
    creation_date = Column('creationDate', Text, index=True)
    # digitizationDate = Column(DateTime)
    # digitization_date = Column('digitizationDate', DateTime)
    digitization_date = Column('digitizationDate', Text)
    orientation = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)
    format = Column(Text)
    # colorDepth = Column(Integer)
    colorDepth = Column('colorDepth', Integer)
    # colorModel = Column(Integer)
    colorModel = Column('colorModel', Integer)


def image(filename):
    try:
        image = session.query(Image).filter_by(name=filename)[0]
    except Exception as e:
        print(e)
        image = None

    return image


if __name__ == '__main__':
    images = session.query(Image).filter_by(name='2010-05-16T13.28.11.jpg').all()
    print(list(images))

    image = images[0]
    info = image.info[0]
    print(info.rating)
