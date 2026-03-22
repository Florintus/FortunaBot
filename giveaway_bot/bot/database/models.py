from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, BigInteger
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import ARRAY

Base = declarative_base()


class Giveaway(Base):
    __tablename__ = 'giveaways'
    
    id = Column(Integer, primary_key=True)
    creator_id = Column(BigInteger, nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    
    # Медиа
    photo_file_id = Column(String(200))
    document_file_id = Column(String(200))
    
    # Временные рамки
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    
    # Условия участия
    required_channels = Column(ARRAY(String), nullable=False)  # Список @username или ID каналов
    twitch_channels = Column(ARRAY(String))  # Twitch каналы для проверки
    winners_count = Column(Integer, default=1)
    
    # Канал публикации
    channel_id = Column(String(200))  # @username или -100ID

    # Статус
    is_published = Column(Boolean, default=False)
    is_finished = Column(Boolean, default=False)
    message_id = Column(BigInteger)  # ID сообщения в канале
    
    # Связи
    participants = relationship('Participant', back_populates='giveaway', cascade='all, delete-orphan')
    winners = relationship('Winner', back_populates='giveaway', cascade='all, delete-orphan')
    
    created_at = Column(DateTime, default=datetime.utcnow)


class Participant(Base):
    __tablename__ = 'participants'
    
    id = Column(Integer, primary_key=True)
    giveaway_id = Column(Integer, ForeignKey('giveaways.id', ondelete='CASCADE'))
    user_id = Column(BigInteger, nullable=False)
    username = Column(String(100))
    full_name = Column(String(200))
    joined_at = Column(DateTime, default=datetime.utcnow)
    
    giveaway = relationship('Giveaway', back_populates='participants')


class Winner(Base):
    __tablename__ = 'winners'
    
    id = Column(Integer, primary_key=True)
    giveaway_id = Column(Integer, ForeignKey('giveaways.id', ondelete='CASCADE'))
    user_id = Column(BigInteger, nullable=False)
    username = Column(String(100))
    full_name = Column(String(200))
    selected_at = Column(DateTime, default=datetime.utcnow)
    
    giveaway = relationship('Giveaway', back_populates='winners')


class TwitchLink(Base):
    __tablename__ = 'twitch_links'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    twitch_username = Column(String(100), nullable=False)
    linked_at = Column(DateTime, default=datetime.utcnow)


class UserState(Base):
    __tablename__ = 'user_states'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    state = Column(String(100))
    data = Column(Text)  # JSON данные для FSM
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)