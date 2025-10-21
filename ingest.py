from dotenv import load_dotenv
import os
from couchbase.cluster import Cluster
from couchbase.auth import PasswordAuthenticator
from couchbase.options import ClusterOptions

from datetime import timedelta
from tqdm import tqdm
import uuid
import pandas as pd
import logging
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# Load environment variables
load_dotenv(override=True)
DB_CONN_STR = os.getenv("DB_CONN_STR")
DB_USERNAME = os.getenv("DB_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_BUCKET = os.getenv("DB_BUCKET")
DB_SCOPE = os.getenv("DB_SCOPE")
DB_COLLECTION = os.getenv("DB_COLLECTION")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
MOVIES_DATASET = "imdb_top_1000.csv"

# Use text-embedding-004 as the embedding model if not set
if not EMBEDDING_MODEL:
    EMBEDDING_MODEL = "models/text-embedding-004"


def check_environment_variable(variable_name):
    """Check if environment variable is set"""
    if variable_name not in os.environ:
        raise ValueError(
            f"{variable_name} environment variable is not set. Please add it to the environment"
        )


# Ensure that all environment variables are set
check_environment_variable("GOOGLE_API_KEY")
check_environment_variable("DB_CONN_STR")
check_environment_variable("DB_USERNAME")
check_environment_variable("DB_PASSWORD")
check_environment_variable("DB_BUCKET")
check_environment_variable("DB_SCOPE")
check_environment_variable("DB_COLLECTION")

# Initialize the embeddings model
embeddings = GoogleGenerativeAIEmbeddings(
    model=EMBEDDING_MODEL,
    google_api_key=os.getenv("GOOGLE_API_KEY")
)


def connect_to_couchbase(connection_string, db_username, db_password):
    """Connect to couchbase"""
    print("Connecting to couchbase...")
    auth = PasswordAuthenticator(db_username, db_password)
    options = ClusterOptions(auth)
    connect_string = connection_string
    cluster = Cluster(connect_string, options)

    # Wait until the cluster is ready for use.
    cluster.wait_until_ready(timedelta(seconds=5))

    return cluster


def generate_embeddings(input_data: str):
    """Generate embeddings using Google GenAI via LangChain"""
    return embeddings.embed_query(input_data)


try:
    cluster = connect_to_couchbase(DB_CONN_STR, DB_USERNAME, DB_PASSWORD)
    bucket = cluster.bucket(f"{DB_BUCKET}")
    scope = bucket.scope(DB_SCOPE)
    collection = scope.collection(DB_COLLECTION)
    data = pd.read_csv(MOVIES_DATASET)

    # Convert columns to numeric types
    data["Gross"] = data["Gross"].str.replace(",", "").astype(float)

    # Fill empty values
    data["Gross"] = data["Gross"].fillna(0)
    data["Certificate"] = data["Certificate"].fillna("NA")
    data["Meta_score"] = data["Meta_score"].fillna(-1)

    data_in_dict = data.to_dict(orient="records")
    print("Ingesting Data...")
    for row in tqdm(data_in_dict):
        try:
            row["Overview_embedding"] = generate_embeddings(row["Overview"])
        except Exception as e:
            print(f"Error while generating embeddings for {row['Series_Title']}", e)
            continue
        doc_id = uuid.uuid4().hex
        collection.upsert(doc_id, row)

except Exception as e:
    print("Error while ingesting data", e)