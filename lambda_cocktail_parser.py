import os
import logging
import spacy
import re
import tarfile
import boto3
from botocore.exceptions import ClientError
from pathlib import Path

MODEL = os.environ.get('MODEL')
DEST = '/tmp'
S3_BUCKET = os.environ.get('S3_BUCKET')
DYNAMO_URL = os.environ.get('DYNAMO_URL')
DESCRIPTIONS_DYNAMO_TABLE = os.environ.get('DESCRIPTIONS_DYNAMO_TABLE')
COCKTAILS_DYNAMO_TABLE = os.environ.get('COCKTAILS_DYNAMO_TABLE')

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def makedir_if_not_exists(DEST):
    if not os.path.exists(DEST):
        os.makedirs(DEST)


def download_model_from_s3(bucket, model, DEST):
    logger.info(f"Downloading {model} from S3: {bucket}")
    makedir_if_not_exists(Path(DEST))
    filename = os.path.join(Path(DEST), f'{model}.tar.gz')

    # download model
    object_name = f'models/{model}.tar.gz'
    s3 = boto3.client('s3')
    s3.download_file(bucket, object_name, filename)
    unzip_file(filename, DEST)
    uncompressed_file = os.path.join(Path(DEST), model)
    logger.info(f"Downloaded to {uncompressed_file}")


def unzip_file(filename, DEST):
    logger.info(f"Unzipping {filename}")
    with tarfile.open(filename) as f:
        f.extractall(path=DEST)


def parse_cocktails(description):
    model_dir = Path(DEST + '/model/')
    result = []

    # Load the saved model and predict
    logger.info(f"Loading model from {model_dir}")
    nlp = spacy.load(model_dir)
    paragrafs = description.split("\n\n")

    for paragraf in paragrafs:
        sentences = paragraf.split("\n")
        cocktail = {
            "name": "",
            "ingredients": [],
            "steps": []
        }

        for sentence in sentences:
            # remove time
            sentence = re.sub(
                r'(2[0-3]|[01]?[0-9]):([0-5]?[0-9])', "", sentence)
            doc = nlp(sentence + '.')

            # Find all named entities in a sentence
            entities = [(ent.label_, ent.text) for ent in doc.ents]
            # print(entities)

            # Check if entities contain cocktail name
            cocktails = [ent[1] for ent in entities if ent[0] == "COCKTAIL"]
            if cocktail["name"] == "" and len(cocktails) > 0:
                cocktail.update({"name": cocktails[0]})
                continue

            # Check if entities contain step
            steps = [ent[1] for ent in entities if ent[0] == "STEP"]
            if len(steps) > 0:
                cocktail["steps"].append(sentence)
                continue

            # Check if entities contain ingredient
            # Check for quantities
            # Add ingredient and quantities to dict
            ings = [ent[1] for ent in entities if ent[0] == "ING"]
            if len(ings) > 0:
                ingredient = {}
                ingredient["name"] = ings[0]
                quantities = [ent[1]
                              for ent in entities if ent[0] == "QUANTITY"]
                ingredient["quantities"] = quantities
                cocktail["ingredients"].append(ingredient)
        if cocktail["name"] != "" and len(cocktail["ingredients"]) > 0:
            result.append(cocktail)

    return result


def load_cocktails(cocktails, dynamo_url, dynamo_table):
    dynamodb = boto3.resource('dynamodb', endpoint_url=dynamo_url)
    table = dynamodb.Table(dynamo_table)
    for cocktail in cocktails:
        logger.info(f"Loading {cocktail['name']} into table {table}")
        table.put_item(Item=cocktail)


def get_description(id, dynamo_url, dynamo_table):
    dynamodb = boto3.resource('dynamodb', endpoint_url=dynamo_url)

    table = dynamodb.Table(dynamo_table)

    try:
        response = table.get_item(Key={'id': id})
    except ClientError as e:
        logger.error(e.response['Error']['Message'])
    else:
        logger.info(f"Response: {response}")
        return response['Item']['description']


def lambda_handler(event, context):
    logger.info(f"Event: {event}")

    download_model_from_s3(S3_BUCKET, MODEL, DEST)

    for record in event['Records']:
        if record['eventName'] in ['MODIFY', 'INSERT']:
            description = get_description(
                record['dynamodb']['Keys']['id']['S'], DYNAMO_URL,
                DESCRIPTIONS_DYNAMO_TABLE)
            logger.info("Parsing data")
            cocktails = parse_cocktails(description)
            logger.info(f"Cocktails: {cocktails}")
            load_cocktails(cocktails, DYNAMO_URL, COCKTAILS_DYNAMO_TABLE)
