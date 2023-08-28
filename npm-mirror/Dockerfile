# Use an official Python runtime as the base image
FROM python:3.8

# Install the parallel command-line tool
RUN apt-get update && apt-get install -y parallel

# Set the working directory in the container
WORKDIR /npm-mirror

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install -r requirements.txt

# Copy the rest of the application code into the container
COPY ./app ./app

# Copy the shell script
COPY run_scripts.sh .

# Make the shell script executable
RUN chmod +x run_scripts.sh

# Run the shell script
CMD ["./run_scripts.sh"]
