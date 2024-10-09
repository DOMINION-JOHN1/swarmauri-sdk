from typing import List, Union, Literal, Dict, Any, Optional
import os
import json
import duckdb
from pydantic import Field, PrivateAttr
import logging

from swarmauri.vectors.concrete.Vector import Vector
from swarmauri.documents.concrete.Document import Document
from swarmauri.embeddings.concrete.Doc2VecEmbedding import Doc2VecEmbedding
from swarmauri.distances.concrete.CosineDistance import CosineDistance

from swarmauri.vector_stores.base.VectorStoreBase import VectorStoreBase
from swarmauri.vector_stores.base.VectorStoreRetrieveMixin import (
    VectorStoreRetrieveMixin,
)
from swarmauri.vector_stores.base.VectorStoreSaveLoadMixin import (
    VectorStoreSaveLoadMixin,
)


class DuckDBVectorStore(
    VectorStoreSaveLoadMixin,
    VectorStoreRetrieveMixin,
    VectorStoreBase,
):
    """A vector store implementation using DuckDB as the backend."""

    type: Literal["DuckDBVectorStore"] = "DuckDBVectorStore"
    database_name: str = Field(
        default=":memory:", description="Name of the DuckDB database"
    )
    table_name: str = Field(
        default="documents", description="Name of the table to store documents"
    )
    embed_dim: Optional[int] = Field(
        default=None, description="Dimension of the embedding vectors"
    )
    persist_dir: str = Field(
        default="./storage", description="Directory to persist the database"
    )

    _conn: Any = PrivateAttr(default=None)
    _is_initialized: bool = PrivateAttr(default=False)
    _database_path: Optional[str] = PrivateAttr(default=None)

    def __init__(self, **data):
        super().__init__(**data)
        self._embedder = Doc2VecEmbedding(vector_size=100)
        self._distance = CosineDistance()

        if self.database_name == ":memory:":
            self._conn = duckdb.connect(self.database_name)
            self._setup_extensions(self._conn)
        else:
            if not os.path.exists(self.persist_dir):
                os.makedirs(self.persist_dir)
            self._database_path = os.path.join(self.persist_dir, self.database_name)

    @staticmethod
    def _setup_extensions(conn):
        conn.install_extension("json")
        conn.load_extension("json")
        conn.install_extension("fts")
        conn.load_extension("fts")

    def connect(self) -> None:
        """Connect to the DuckDB database and initialize if necessary."""
        if not self._is_initialized:
            if self.database_name == ":memory:":
                self._initialize_table(self._conn)
            else:
                with duckdb.connect(self._database_path) as conn:
                    self._setup_extensions(conn)
                    self._initialize_table(conn)
            self._is_initialized = True

    def _initialize_table(self, conn) -> None:
        embed_dim_str = f"[{self.embed_dim}]" if self.embed_dim else "[]"
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id VARCHAR PRIMARY KEY,
                content TEXT,
                embedding FLOAT{embed_dim_str},
                metadata JSON
            )
        """
        )

    def disconnect(self) -> None:
        """Disconnect from the DuckDB database."""
        if self._conn and self.database_name == ":memory:":
            self._conn.close()
            self._conn = None
        self._is_initialized = False

    def _prepare_document(self, document: Document) -> Dict[str, Any]:
        if not document.embedding:
            self._embedder.fit([document.content])
            embedding = (
                self._embedder.transform([document.content])[0].to_numpy().tolist()
            )
        else:
            embedding = (
                document.embedding.value
                if isinstance(document.embedding, Vector)
                else document.embedding
            )

        return {
            "id": document.id,
            "content": document.content,
            "embedding": embedding,
            "metadata": json.dumps(document.metadata or {}),
        }

    def add_document(self, document: Document) -> None:
        # self.connect()
        data = self._prepare_document(document)
        query = f"""
            INSERT OR REPLACE INTO {self.table_name} (id, content, embedding, metadata)
            VALUES (?, ?, ?, ?)
        """
        if self.database_name == ":memory:":
            self._conn.execute(
                query,
                [data["id"], data["content"], data["embedding"], data["metadata"]],
            )
        else:
            with duckdb.connect(self._database_path) as conn:
                conn.execute(
                    query,
                    [data["id"], data["content"], data["embedding"], data["metadata"]],
                )

    def add_documents(self, documents: List[Document]) -> None:
        ids = [doc.id for doc in documents]
        contents = [doc.content for doc in documents]

        # the for loop should only be called once when fitting the embedder
        self._embedder.fit([doc.content for doc in documents])

        embeddings = [
            self._embedder.transform([doc.content])[0].to_numpy().tolist()
            for doc in documents
        ]

        metadatas = [doc.metadata for doc in documents]

        data_list = list(zip(ids, contents, embeddings, metadatas))

        query = f"""
            INSERT OR REPLACE INTO {self.table_name} (id, content, embedding, metadata) 
            VALUES (?, ?, ?, ?)
        """

        if self.database_name == ":memory:":
            self._conn.executemany(
                query,
                data_list,
            )
        else:
            with duckdb.connect(self._database_path) as conn:
                conn.executemany(
                    query,
                    data_list,
                )

        # for document in documents:
        #     self.add_document(document)

    def get_document(self, id: str) -> Optional[Document]:
        # self.connect()
        query = f"SELECT id, content, metadata FROM {self.table_name} WHERE id = ?"
        if self.database_name == ":memory:":
            result = self._conn.execute(query, [id]).fetchone()
        else:
            with duckdb.connect(self._database_path) as conn:
                result = conn.execute(query, [id]).fetchone()

        if result:
            return Document(
                id=result[0], content=result[1], metadata=json.loads(result[2])
            )
        return None

    def retrieve(self, query: str, top_k: int = 5) -> List[Document]:
        # self.connect()
        query_embedding = self._embedder.transform([query])[0].value
        cosine_sim_query = f"""
            SELECT id, content, metadata,
                   list_cosine_similarity(embedding, ?) as similarity
            FROM {self.table_name}
            ORDER BY similarity DESC
            LIMIT ?
        """
        if self.database_name == ":memory:":
            results = self._conn.execute(
                cosine_sim_query, [query_embedding, top_k]
            ).fetchall()
        else:
            with duckdb.connect(self._database_path) as conn:
                results = conn.execute(
                    cosine_sim_query, [query_embedding, top_k]
                ).fetchall()

        logging.info(f"results: {results}")

        return [
            Document(
                id=row[0],
                content=row[1],
                metadata=json.loads(row[2]),
                embedding=Vector(value=[row[3]]),
            )
            for row in results
        ]

    def delete_document(self, id: str) -> None:
        # self.connect()
        query = f"DELETE FROM {self.table_name} WHERE id = ?"
        if self.database_name == ":memory:":
            self._conn.execute(query, [id])
        else:
            with duckdb.connect(self._database_path) as conn:
                conn.execute(query, [id])

    def get_all_documents(self) -> List[Document]:
        # self.connect()
        query = f"SELECT id, content, metadata FROM {self.table_name}"
        if self.database_name == ":memory:":
            results = self._conn.execute(query).fetchall()
        else:
            with duckdb.connect(self._database_path) as conn:
                results = conn.execute(query).fetchall()

        return [
            Document(id=row[0], content=row[1], metadata=json.loads(row[2]))
            for row in results
        ]

    def update_document(self, id: str, new_document: Document) -> None:
        """Update an existing document in the DuckDB store."""
        try:
            data = self._prepare_document(new_document)
            self._client.execute(
                """
                UPDATE documents
                SET content = ?, embedding = ?, metadata = ?
                WHERE id = ?
                """,
                [data["content"], data["embedding"], data["metadata"], id],
            )
        except Exception as e:
            raise RuntimeError(f"Failed to update document {id}: {str(e)}")

    @classmethod
    def from_local(cls, database_path: str, table_name: str = "documents", **kwargs):
        """Load a DuckDBVectorStore from a local file."""
        database_name = os.path.basename(database_path)
        persist_dir = os.path.dirname(database_path)
        return cls(
            database_name=database_name,
            table_name=table_name,
            persist_dir=persist_dir,
            **kwargs,
        )

    def model_dump_json(self, *args, **kwargs) -> str:
        """Override model_dump_json to ensure connection is closed before serialization."""
        self.disconnect()
        return super().model_dump_json(*args, **kwargs)
