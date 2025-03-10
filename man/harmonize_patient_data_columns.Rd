% Generated by roxygen2: do not edit by hand
% Please edit documentation in R/script1_helper_read_patient_data.R
\name{harmonize_patient_data_columns}
\alias{harmonize_patient_data_columns}
\title{Harmonize patient data column names.}
\usage{
harmonize_patient_data_columns(patient_df, columns_synonyms)
}
\arguments{
\item{patient_df}{data.frame holding the patient data of the month sheet of a tracker.}

\item{columns_synonyms}{data.frame with synonyms for tracker variables.}
}
\value{
data.frame with harmonized column names.
}
\description{
Imports the patient df, cleans it and matches it against
column synonyms to unify column names
}
