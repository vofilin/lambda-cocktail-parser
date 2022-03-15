FROM public.ecr.aws/lambda/python:3.9

# Install the function's dependencies
COPY requirements.txt  .
RUN  pip install -r requirements.txt

# Copy function code
COPY lambda_cocktail_parser.py .

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD [ "lambda_cocktail_parser.lambda_handler" ]
