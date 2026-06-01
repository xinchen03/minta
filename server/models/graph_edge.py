"""Graph edges — cosine similarity between context objects for cold-start initialization."""
from sqlalchemy import Column, Integer, String, Float
from config import Base


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    context_id_a = Column(String(100), nullable=False)
    context_id_b = Column(String(100), nullable=False)
    weight = Column(Float, nullable=False, default=0.0)
