#!/usr/bin/env Rscript

# Debug the full pipeline to find where it fails
library(arrow)
library(dplyr)
library(tidyselect)

# Load the package
devtools::load_all(".")

# Setup error values
ERROR_VAL_NUMERIC <<- 999999
ERROR_VAL_CHARACTER <<- "Undefined"
ERROR_VAL_DATE <<- "9999-09-09"

# Read the raw parquet
df_raw <- read_parquet("/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/output/patient_data_raw/2024_Sibu Hospital A4D Tracker_patient_raw.parquet")

cat("Step 1: Load schema and merge\n")
schema <- tibble::tibble(
    age = integer(),
    analog_insulin_long_acting = character(),
    analog_insulin_rapid_acting = character(),
    blood_pressure_dias_mmhg = integer(),
    blood_pressure_sys_mmhg = integer(),
    blood_pressure_updated = lubridate::as_date(1),
    bmi = numeric(),
    bmi_date = lubridate::as_date(1),
    clinic_id = character(),
    clinic_visit = character(),
    complication_screening_eye_exam_date = lubridate::as_date(1),
    complication_screening_eye_exam_value = character(),
    complication_screening_foot_exam_date = lubridate::as_date(1),
    complication_screening_foot_exam_value = character(),
    complication_screening_kidney_test_date = lubridate::as_date(1),
    complication_screening_kidney_test_value = character(),
    complication_screening_lipid_profile_cholesterol_value = character(),
    complication_screening_lipid_profile_date = lubridate::as_date(1),
    complication_screening_lipid_profile_hdl_mmol_value = numeric(),
    complication_screening_lipid_profile_hdl_mg_value = numeric(),
    complication_screening_lipid_profile_ldl_mmol_value = numeric(),
    complication_screening_lipid_profile_ldl_mg_value = numeric(),
    complication_screening_lipid_profile_triglycerides_value = numeric(),
    complication_screening_remarks = character(),
    complication_screening_thyroid_test_date = lubridate::as_date(1),
    complication_screening_thyroid_test_ft4_pmol_value = numeric(),
    complication_screening_thyroid_test_ft4_ng_value = numeric(),
    complication_screening_thyroid_test_tsh_value = numeric(),
    dm_complication_eye = character(),
    dm_complication_kidney = character(),
    dm_complication_others = character(),
    dm_complication_remarks = character(),
    dob = lubridate::as_date(1),
    edu_occ = character(),
    edu_occ_updated = lubridate::as_date(1),
    family_history = character(),
    fbg_baseline_mg = numeric(),
    fbg_baseline_mmol = numeric(),
    fbg_updated_date = lubridate::as_date(1),
    fbg_updated_mg = numeric(),
    fbg_updated_mmol = numeric(),
    file_name = character(),
    hba1c_baseline = numeric(),
    hba1c_baseline_exceeds = logical(),
    hba1c_updated = numeric(),
    hba1c_updated_exceeds = logical(),
    hba1c_updated_date = lubridate::as_date(1),
    height = numeric(),
    hospitalisation_cause = character(),
    hospitalisation_date = lubridate::as_date(1),
    human_insulin_intermediate_acting = character(),
    human_insulin_pre_mixed = character(),
    human_insulin_short_acting = character(),
    insulin_injections = numeric(),
    insulin_regimen = character(),
    insulin_total_units = numeric(),
    insulin_type = character(),
    insulin_subtype = character(),
    last_clinic_visit_date = lubridate::as_date(1),
    last_remote_followup_date = lubridate::as_date(1),
    lost_date = lubridate::as_date(1),
    name = character(),
    observations = character(),
    observations_category = character(),
    other_issues = character(),
    patient_consent = character(),
    patient_id = character(),
    province = character(),
    recruitment_date = lubridate::as_date(1),
    remote_followup = character(),
    sex = character(),
    sheet_name = character(),
    status = character(),
    status_out = character(),
    support_level = character(),
    t1d_diagnosis_age = integer(),
    t1d_diagnosis_date = lubridate::as_date(1),
    t1d_diagnosis_with_dka = character(),
    testing_frequency = integer(),
    tracker_date = lubridate::as_date(1),
    tracker_month = integer(),
    tracker_year = integer(),
    weight = numeric()
)

# Add missing columns
df_patient <- merge.default(df_raw, schema, all.x = TRUE)
df_patient <- df_patient[colnames(schema)]
cat(sprintf("  Shape: %d rows, %d cols\n", nrow(df_patient), ncol(df_patient)))

cat("\nStep 2: Pre-processing (fix known problems)\n")
df_step2 <- df_patient %>%
    rowwise() %>%
    mutate(
        hba1c_baseline = stringr::str_replace(hba1c_baseline, "<|>", ""),
        hba1c_updated = stringr::str_replace(hba1c_updated, "<|>", ""),
        fbg_updated_mg = fix_fbg(fbg_updated_mg),
        fbg_updated_mmol = fix_fbg(fbg_updated_mmol),
        testing_frequency = fix_testing_frequency(testing_frequency, patient_id),
        analog_insulin_long_acting = sub("-", "N", analog_insulin_long_acting, fixed = TRUE),
        analog_insulin_rapid_acting = sub("-", "N", analog_insulin_rapid_acting, fixed = TRUE),
        human_insulin_intermediate_acting = sub("-", "N", human_insulin_intermediate_acting, fixed = TRUE),
        human_insulin_pre_mixed = sub("-", "N", human_insulin_pre_mixed, fixed = TRUE),
        human_insulin_short_acting = sub("-", "N", human_insulin_short_acting, fixed = TRUE)
    )
cat("  ✅ Step 2 complete\n")

cat("\nStep 3: Type conversions\n")
cat("  Converting numeric columns...\n")
df_step3 <- df_step2 %>%
    mutate(
        across(
            schema %>% select(where(is.numeric)) %>% names(),
            \(x) convert_to(correct_decimal_sign(x), as.numeric, ERROR_VAL_NUMERIC, cur_column(), id = patient_id)
        )
    )
cat("  ✅ Numeric conversion complete\n")

cat("  Converting logical columns...\n")
df_step3 <- df_step3 %>%
    mutate(
        across(
            schema %>% select(where(is.logical)) %>% names(),
            \(x) convert_to(x, as.logical, FALSE, cur_column(), id = patient_id)
        )
    )
cat("  ✅ Logical conversion complete\n")

cat("  Converting date columns...\n")
df_step3 <- df_step3 %>%
    mutate(
        across(
            schema %>% select(where(lubridate::is.Date)) %>% names(),
            \(x) convert_to(fix_digit_date(x), parse_dates, as.Date(ERROR_VAL_DATE), cur_column(), id = patient_id)
        )
    )
cat("  ✅ Date conversion complete\n")

cat("  Converting integer columns...\n")
df_step3 <- df_step3 %>%
    mutate(
        across(
            schema %>% select(where(is.integer)) %>% names(),
            \(x) convert_to(x, function(x) as.integer(round(as.double(x))), ERROR_VAL_NUMERIC, cur_column(), id = patient_id)
        )
    )
cat("  ✅ Integer conversion complete\n")

cat("\nStep 4: Post-processing transformations\n")
cat("  Attempting height transformation...\n")
df_step4 <- df_step3 %>%
    mutate(
        height = transform_cm_to_m(height) %>%
            cut_numeric_value(min = 0, max = 2.3, col_name = "height")
    )
cat("  ✅ Height transformation complete\n")

cat("\nSample heights after transformation:\n")
print(df_step4$height[1:5])

cat("\n✅ Full pipeline test successful!\n")
