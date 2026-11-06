import os
from dotenv import load_dotenv

load_dotenv()

GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
LISTING_URL =os.environ["AMAZON_LISTING_URL"]