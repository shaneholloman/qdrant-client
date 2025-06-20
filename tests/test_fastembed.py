import pytest

from qdrant_client import QdrantClient, models
from qdrant_client.client_base import QdrantBase
from tests.congruence_tests.test_common import compare_client_results

from tests.utils import read_version


DOCS_EXAMPLE = {
    "documents": [
        "Qdrant has Langchain integrations",
        "Qdrant also has Llama Index integrations",
    ],
    "metadata": [{"source": "Langchain-docs"}, {"source": "LlamaIndex-docs"}],
    "ids": [42, 2000],
}


def test_dense():
    local_client = QdrantClient(":memory:")
    collection_name = "demo_collection"
    docs = [
        "Qdrant has Langchain integrations",
        "Qdrant also has Llama Index integrations",
    ]

    if not local_client._FASTEMBED_INSTALLED:
        with pytest.raises(ImportError):
            local_client.add(collection_name, docs)
    else:
        local_client.add(collection_name=collection_name, documents=docs)
        assert local_client.count(collection_name).count == 2

        local_client.add(collection_name=collection_name, **DOCS_EXAMPLE)
        assert local_client.count(collection_name).count == 4

        id_ = DOCS_EXAMPLE["ids"][0]
        record = local_client.retrieve(collection_name, ids=[id_])[0]
        assert record.payload == {
            "document": DOCS_EXAMPLE["documents"][0],
            **DOCS_EXAMPLE["metadata"][0],
        }

        search_result = local_client.query(
            collection_name=collection_name, query_text="This is a query document"
        )

        assert len(search_result) > 0


def test_hybrid_query():
    local_client = QdrantClient(":memory:")
    collection_name = "hybrid_collection"

    if not local_client._FASTEMBED_INSTALLED:
        pytest.skip("FastEmbed is not installed, skipping test")

    local_client.set_sparse_model(embedding_model_name="prithivida/Splade_PP_en_v1")

    local_client.add(collection_name=collection_name, **DOCS_EXAMPLE)

    hybrid_search_result = local_client.query(
        collection_name=collection_name, query_text="This is a query document"
    )

    assert len(hybrid_search_result) > 0

    local_client.set_sparse_model(None)
    dense_search_result = local_client.query(
        collection_name=collection_name, query_text="This is a query document"
    )
    assert len(dense_search_result) > 0

    assert (
        hybrid_search_result[0].score != dense_search_result[0].score
    )  # hybrid search has score from fusion


def test_query_batch():
    local_client = QdrantClient(":memory:")

    dense_collection_name = "dense_collection"
    hybrid_collection_name = "hybrid_collection"

    if not local_client._FASTEMBED_INSTALLED:
        pytest.skip("FastEmbed is not installed, skipping test")

    local_client.add(collection_name=dense_collection_name, **DOCS_EXAMPLE)
    query_texts = ["This is a query document", "This is another query document"]
    dense_search_result = local_client.query_batch(
        collection_name=dense_collection_name, query_texts=query_texts
    )
    assert len(dense_search_result) == len(query_texts)
    assert all(len(result) > 0 for result in dense_search_result)

    local_client.set_sparse_model(embedding_model_name="prithivida/Splade_PP_en_v1")

    local_client.add(collection_name=hybrid_collection_name, **DOCS_EXAMPLE)

    hybrid_search_result = local_client.query_batch(
        collection_name=hybrid_collection_name, query_texts=query_texts
    )

    assert len(hybrid_search_result) == len(query_texts)
    assert all(len(result) > 0 for result in hybrid_search_result)

    single_dense_response = next(iter(dense_search_result))
    single_hybrid_response = next(iter(hybrid_search_result))

    assert (
        single_hybrid_response[0].score != single_dense_response[0].score
    )  # hybrid search has score from fusion


def test_set_model():
    local_client = QdrantClient(":memory:")
    collection_name = "demo_collection"
    embedding_model_name = "sentence-transformers/all-MiniLM-L6-v2"
    if not local_client._FASTEMBED_INSTALLED:
        pytest.skip("FastEmbed is not installed, skipping test")

    local_client.set_model(
        embedding_model_name=embedding_model_name,
    )

    # Check if the model is initialized & cls.embeddings_models is set with expected values
    dim, dist = local_client._get_model_params(embedding_model_name)
    assert dim == 384

    # Use the initialized model to add documents with vector embeddings
    local_client.add(collection_name=collection_name, **DOCS_EXAMPLE)
    assert local_client.count(collection_name).count == 2


@pytest.mark.parametrize("prefer_grpc", (False, True))
def test_query_interface(prefer_grpc: bool):
    def query_call(
        client: QdrantBase, cn: str, doc: models.Document, using: str
    ) -> models.QueryResponse:
        return client.query_points(cn, doc, using)

    local_client = QdrantClient(":memory:")
    if not local_client._FASTEMBED_INSTALLED:
        pytest.skip("FastEmbed is not installed, skipping test")

    sparse_model_name = "Qdrant/bm25"
    remote_client = QdrantClient(prefer_grpc=prefer_grpc)
    remote_client.set_sparse_model(sparse_model_name)
    local_client.set_sparse_model(sparse_model_name)

    collection_name = "fastembed-test-query-collection"
    if remote_client.collection_exists(collection_name):
        remote_client.delete_collection(collection_name)

    local_client.add(collection_name, **DOCS_EXAMPLE)
    remote_client.add(collection_name, **DOCS_EXAMPLE)

    assert local_client.count(collection_name).count == len(DOCS_EXAMPLE["documents"])
    for model_name, vector_field_name in (
        (remote_client.DEFAULT_EMBEDDING_MODEL, remote_client.get_vector_field_name()),
        (sparse_model_name, remote_client.get_sparse_vector_field_name()),
    ):
        document = models.Document(
            text="Does Qdrant has a Llama Index integration?", model=model_name
        )

        compare_client_results(
            local_client,
            remote_client,
            query_call,
            using=vector_field_name,
            cn=collection_name,
            doc=document,
        )


def test_idf_models():
    local_client = QdrantClient(":memory:")

    if not local_client._FASTEMBED_INSTALLED:
        pytest.skip("FastEmbed is not installed, skipping")

    major, minor, patch, dev = read_version()
    if not dev and None not in (major, minor, patch) and (major, minor, patch) < (1, 10, 2):
        pytest.skip("Works as of version 1.10.2")

    for model_name in ("Qdrant/bm25", "Qdrant/bm42-all-minilm-l6-v2-attentions"):
        local_client.set_sparse_model(model_name)
        collection_name = model_name.split("/")[-1].replace("-", "_")

        local_client.add(collection_name=collection_name, **DOCS_EXAMPLE)
        local_client.query(
            collection_name=collection_name, query_text="Qdrant and Llama Index integration"
        )

        collection_info = local_client.get_collection(collection_name=collection_name)
        vector_name = local_client.get_sparse_vector_field_name()
        modifier = collection_info.config.params.sparse_vectors[vector_name].modifier
        assert modifier == models.Modifier.IDF

    # the only sparse model without IDF is SPLADE, however it's too large for tests, so we don't test how non-idf
    # models work


def test_get_embedding_size():
    local_client = QdrantClient(":memory:")

    if not local_client._FASTEMBED_INSTALLED:
        pytest.skip("FastEmbed is not installed, skipping test")

    assert local_client.get_embedding_size() == 384

    assert local_client.get_embedding_size(model_name="BAAI/bge-base-en-v1.5") == 768

    assert local_client.get_embedding_size(model_name="Qdrant/resnet50-onnx") == 2048

    assert local_client.get_embedding_size(model_name="colbert-ir/colbertv2.0") == 128

    with pytest.raises(
        ValueError, match="Sparse embeddings do not return fixed embedding size and distance type"
    ):
        local_client.get_embedding_size(model_name="Qdrant/bm25")
