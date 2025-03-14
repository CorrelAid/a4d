% Generated by roxygen2: do not edit by hand
% Please edit documentation in R/script2_sanitize_str.R
\name{sanitize_str}
\alias{sanitize_str}
\title{Sanitize column name}
\usage{
sanitize_str(text)
}
\arguments{
\item{text}{A text to be sanitized.}
}
\value{
The sanitized text.
}
\description{
This function takes in a string,
sanitizes it by converting all letters to lower case,
removing all spaces and special characters except alphanumeric characters,
and then returns the sanitized string.
}
\examples{
sanitize_str("John Doe's Column") # should return "johndoescolumn"
sanitize_str("Date 2022") # should return "date2022"
sanitize_str("My Awesome 1st Column!!") # should return "myawesome1stcolumn"

}
