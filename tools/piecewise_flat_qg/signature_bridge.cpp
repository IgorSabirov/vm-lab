// SPDX-License-Identifier: GPL-3.0-or-later
// vm-lab adapter; the numerical implementation is the unmodified Zenodo library.
#include "symmetric_matrix_signature.hpp"
#include <cstddef>
#include <cstdint>
#include <new>

extern "C" int vm_signature_batch(
    const double *input, std::size_t batch, std::size_t n,
    int *statuses, std::size_t *counts, double *cutoffs,
    std::uint8_t *flags) noexcept {
  if(!input || !statuses || !counts || !cutoffs || !flags ||
     n == 0 || n > 256 || batch == 0 || batch > 1000000)
    return 1;
  try {
    matrix_signature::Matrix matrix(n, std::vector<double>(n));
    matrix_signature::Options options;
    options.log_stream = nullptr;
    for(std::size_t b = 0; b < batch; ++b) {
      for(std::size_t i = 0; i < n; ++i)
        for(std::size_t j = 0; j < n; ++j)
          matrix[i][j] = input[(b*n+i)*n+j];
      const auto result = matrix_signature::calculate_matrix_signature(matrix, options);
      statuses[b] = static_cast<int>(result.status);
      counts[3*b] = result.signature.positive;
      counts[3*b+1] = result.signature.negative;
      counts[3*b+2] = result.signature.zero;
      cutoffs[b] = result.zero_tolerance;
      flags[3*b] = result.reliable();
      flags[3*b+1] = result.symmetry_adjusted;
      flags[3*b+2] = result.numerically_ambiguous;
    }
    return 0;
  } catch(const std::bad_alloc &) {
    return 2;
  } catch(...) {
    return 3;
  }
}
