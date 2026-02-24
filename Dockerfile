FROM rocker/r-ver:4.5.1

# Install system dependencies required by R packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    apt-transport-https \
    ca-certificates \
    gnupg \
    curl \
    libssl-dev \
    libxml2-dev \
    libcurl4-openssl-dev \
    libfontconfig1-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libfreetype6-dev \
    libpng-dev \
    libtiff5-dev \
    libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Google Cloud SDK (provides gsutil and bq)
RUN curl https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    | tee /etc/apt/sources.list.d/google-cloud-sdk.list \
    && apt-get update && apt-get install -y --no-install-recommends google-cloud-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy renv infrastructure first to leverage Docker layer caching for packages
COPY renv.lock renv.lock
COPY .Rprofile .Rprofile
COPY renv/activate.R renv/activate.R
COPY renv/settings.json renv/settings.json

# Install renv
RUN R -e "install.packages('renv', repos = 'https://cloud.r-project.org')"

# Restore all R packages declared in renv.lock
RUN R -e "renv::restore()"

# Copy the rest of the application
COPY . .

# Use the cloud-run configuration profile
ENV R_CONFIG_ACTIVE=cloud-run

ENTRYPOINT ["Rscript", "scripts/R/run_pipeline.R"]
