/* R143: thin interface to the unmodified upstream HYREC-2 SWIFT solver.
 * Compile the upstream sources with their supported -DCAMB switch.
 * The only substitutions are a supplied expansion history and explicitly
 * requested abundance conventions; all atomic/radiative code stays upstream.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "history.h"

typedef double (*hubble_fn)(double z);
static hubble_fn common_hubble = NULL;
static unsigned long hubble_calls = 0;

void r143_set_hubble(hubble_fn function) { common_hubble = function; }

/* history.c's native CAMB bridge converts this back with the same constants.
 * These factors therefore cancel: the solver receives exactly H_callback(z).
 */
double exported_dtauda(double *a) {
    if (!common_hubble || !isfinite(*a) || *a <= 0.0) return NAN;
    double hz = common_hubble(1.0 / *a - 1.0);
    hubble_calls++;
    if (!isfinite(hz) || hz <= 0.0) return NAN;
    return 2.99792458e8 / (3.085678e22 * (*a) * (*a) * hz);
}

double r143_probe_hubble(double z) { return rec_HubbleRate(NULL, z); }

static int fail(char *error, int capacity, const char *message, int code) {
    if (error && capacity > 0) snprintf(error, (size_t) capacity, "%s", message);
    return code;
}

/* meta: native_nH0, native_fHe, used_nH0, used_fHe, dlna, Nz,
 *       H_callback_count, model_code, zmax, zmin.
 * nH0 and fHe overrides <=0 preserve upstream conventions.
 */
int r143_hyrec_compute(const char *data_path, const char *parameters_path,
                      double dlna, double common_nH0, double common_fHe,
                      int count, const double *redshifts,
                      double *xe, double *tm, double *meta,
                      char *error, int error_capacity) {
    if (!common_hubble) return fail(error, error_capacity, "Hubble callback missing", 1);
    if (!(dlna > 0.0 && dlna <= DLNA_SWIFT))
        return fail(error, error_capacity, "Require 0 < dlna <= native DLNA_SWIFT", 2);
    if (count < 1) return fail(error, error_capacity, "Empty output grid", 3);
    for (int i = 0; i < count; ++i)
        if (!isfinite(redshifts[i]) || redshifts[i] < 0.0 || redshifts[i] > 8000.0)
            return fail(error, error_capacity, "Output redshift outside [0, 8000]", 4);

    HYREC_DATA data = {0};
    data.path_to_hyrec = (char *) data_path;
    hyrec_allocate(&data, 8000.0, 0.0);
    if (data.error) {
        int status = fail(error, error_capacity, data.error_message, 5);
        hyrec_free(&data);
        return status;
    }
    FILE *parameters = fopen(parameters_path, "r");
    if (!parameters) {
        hyrec_free(&data);
        return fail(error, error_capacity, "Cannot open parameter file", 6);
    }
    rec_get_cosmoparam(parameters, NULL, data.cosmo);
    fclose(parameters);
    meta[0] = data.cosmo->nH0;
    meta[1] = data.cosmo->fHe;
    if (common_nH0 > 0.0) data.cosmo->nH0 = common_nH0;
    if (common_fHe > 0.0) data.cosmo->fHe = common_fHe;

    /* The authors explicitly permit decreasing DLNA_SWIFT (hydrogen.h).
     * Reallocate precisely the arrays whose size depends on it. SWIFT does
     * not allocate the FULL model's radiative-history arrays.
     */
    long new_size = (long) (log(8001.0) / dlna) + 2;
    if (new_size != data.Nz) {
        double *new_xe = calloc((size_t) new_size, sizeof(double));
        double *new_tm = calloc((size_t) new_size, sizeof(double));
        if (!new_xe || !new_tm) {
            free(new_xe); free(new_tm); hyrec_free(&data);
            return fail(error, error_capacity, "History allocation failed", 7);
        }
        free(data.xe_output); free(data.Tm_output);
        data.xe_output = new_xe;
        data.Tm_output = new_tm;
        data.Nz = new_size;
    }
    data.cosmo->dlna = dlna;
    hubble_calls = 0;
    hyrec_compute(&data, SWIFT);
    if (data.error) {
        int status = fail(error, error_capacity, data.error_message, 8);
        hyrec_free(&data);
        return status;
    }
    for (int i = 0; i < count; ++i) {
        xe[i] = hyrec_xe(redshifts[i], &data);
        tm[i] = hyrec_Tm(redshifts[i], &data);
        if (data.error || !isfinite(xe[i]) || !isfinite(tm[i]) || xe[i] <= 0.0 || tm[i] <= 0.0) {
            int status = fail(error, error_capacity, "Invalid output or interpolation error", 9);
            hyrec_free(&data);
            return status;
        }
    }
    meta[2] = data.cosmo->nH0; meta[3] = data.cosmo->fHe;
    meta[4] = data.cosmo->dlna; meta[5] = (double) data.Nz;
    meta[6] = (double) hubble_calls; meta[7] = (double) SWIFT;
    meta[8] = data.zmax; meta[9] = data.zmin;
    hyrec_free(&data);
    if (error && error_capacity > 0) error[0] = '\0';
    return 0;
}
