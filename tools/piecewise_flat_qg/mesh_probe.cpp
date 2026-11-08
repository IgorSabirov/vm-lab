// SPDX-License-Identifier: GPL-3.0-or-later
// Small integration check of the original triangulator API, with no edge sampling.
#include "triangulator.hpp"

int main() {
  triangulator_global::logLevel = LOG_ERROR;
  SimpComp *pair = seed_single_simplex(4, "shared-face-pair");
  attach_new_simplex_to_boundary(pair->elements[3][0], pair);
  const std::size_t expected_pair[] = {6, 14, 16, 9, 2};
  bool passed = true;
  for(int k = 0; k <= 4; ++k)
    passed = passed && pair->elements[k].size() == expected_pair[k];
  if(!passed) { unseed_everything(); return 1; }
  auto *a = pair->elements[4][0];
  auto *b = pair->elements[4][1];
  std::size_t common_edges = 0;
  for(auto *edge : a->neighbors->elements[1])
    if(std::find(b->neighbors->elements[1].begin(),
                 b->neighbors->elements[1].end(), edge) != b->neighbors->elements[1].end())
      ++common_edges;
  passed = passed && common_edges == 6;
  SimpComp *sphere = seed_sphere(4, "sphere-seed");
  const std::size_t expected_sphere[] = {6, 15, 20, 15, 6};
  for(int k = 0; k <= 4; ++k)
    passed = passed && sphere->elements[k].size() == expected_sphere[k];
  for(auto *face : sphere->elements[3])
    passed = passed && face->neighbors->elements[4].size() == 2;
  cout << "{\"passed\":" << (passed ? "true" : "false")
       << ",\"pair_counts\":[6,14,16,9,2],\"shared_edge_objects\":" << common_edges
       << ",\"sphere_counts\":[6,15,20,15,6]}\n";
  unseed_everything();
  return passed ? 0 : 1;
}
