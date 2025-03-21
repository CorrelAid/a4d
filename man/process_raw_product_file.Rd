% Generated by roxygen2: do not edit by hand
% Please edit documentation in R/script2_process_product_data.R
\name{process_raw_product_file}
\alias{process_raw_product_file}
\title{Process raw product data}
\usage{
process_raw_product_file(
  paths,
  product_file,
  product_file_name,
  synonyms_product,
  output_root
)
}
\arguments{
\item{paths}{list of paths to the input and output directories.}

\item{product_file}{name of the raw product data file.}

\item{product_file_name}{base name of the raw product data file.}

\item{synonyms_product}{list of synonyms for the product data.}

\item{output_root}{The root directory of the output folder.}
}
\description{
This function reads the raw product data from a parquet file, cleans the data, and exports the cleaned data as a parquet file.
}
