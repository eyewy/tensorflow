# pylint: disable=g-bad-file-header
# Copyright 2016 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Tests for KMeans."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import tensorflow as tf

from tensorflow.contrib.factorization.python.ops import kmeans as kmeans_ops
from tensorflow.contrib.factorization.python.ops.kmeans import KMeansClustering as KMeans
from tensorflow.contrib.learn.python.learn.estimators import run_config

FLAGS = tf.app.flags.FLAGS


def normalize(x):
  return x / np.sqrt(np.sum(x * x, axis=-1, keepdims=True))


def cosine_similarity(x, y):
  return np.dot(normalize(x), np.transpose(normalize(y)))


class KMeansTest(tf.test.TestCase):

  def setUp(self):
    np.random.seed(3)
    self.num_centers = 5
    self.num_dims = 2
    self.num_points = 10000
    self.true_centers = self.make_random_centers(self.num_centers,
                                                 self.num_dims)
    self.points, _, self.scores = self.make_random_points(
        self.true_centers,
        self.num_points)
    self.true_score = np.add.reduce(self.scores)

    self.kmeans = KMeans(self.num_centers,
                         initial_clusters=kmeans_ops.RANDOM_INIT,
                         batch_size=self.batch_size,
                         use_mini_batch=self.use_mini_batch,
                         steps=30,
                         continue_training=True,
                         config=run_config.RunConfig(tf_random_seed=14),
                         random_seed=12)

  @property
  def batch_size(self):
    return self.num_points

  @property
  def use_mini_batch(self):
    return False

  @staticmethod
  def make_random_centers(num_centers, num_dims):
    return np.round(np.random.rand(num_centers,
                                   num_dims).astype(np.float32) * 500)

  @staticmethod
  def make_random_points(centers, num_points, max_offset=20):
    num_centers, num_dims = centers.shape
    assignments = np.random.choice(num_centers, num_points)
    offsets = np.round(np.random.randn(
        num_points,
        num_dims).astype(np.float32) * max_offset)
    return (centers[assignments] + offsets,
            assignments,
            np.add.reduce(offsets * offsets, 1))

  def test_clusters(self):
    kmeans = self.kmeans
    kmeans.fit(x=self.points, steps=0)
    clusters = kmeans.clusters()
    self.assertAllEqual(list(clusters.shape),
                        [self.num_centers, self.num_dims])

  def test_fit(self):
    if self.batch_size != self.num_points:
      # TODO(agarwal): Doesn't work with mini-batch.
      return
    kmeans = self.kmeans
    kmeans.fit(x=self.points,
               steps=1)
    score1 = kmeans.score(x=self.points)
    kmeans.fit(x=self.points,
               steps=15 * self.num_points // self.batch_size)
    score2 = kmeans.score(x=self.points)
    self.assertTrue(score1 > score2)
    self.assertNear(self.true_score, score2, self.true_score * 0.05)

  def test_infer(self):
    kmeans = self.kmeans
    kmeans.fit(x=self.points)
    clusters = kmeans.clusters()

    # Make a small test set
    points, true_assignments, true_offsets = self.make_random_points(clusters,
                                                                     10)
    # Test predict
    assignments = kmeans.predict(points)
    self.assertAllEqual(assignments, true_assignments)

    # Test score
    score = kmeans.score(points)
    self.assertNear(score, np.sum(true_offsets), 0.01 * score)

    # Test transform
    transform = kmeans.transform(points)
    true_transform = np.maximum(
        0,
        np.sum(np.square(points), axis=1, keepdims=True) -
        2 * np.dot(points, np.transpose(clusters)) +
        np.transpose(np.sum(np.square(clusters), axis=1, keepdims=True)))
    self.assertAllClose(transform, true_transform, rtol=0.05, atol=10)

  def test_fit_with_cosine_distance(self):
    # Create points on y=x and y=1.5x lines to check the cosine similarity.
    # Note that euclidean distance will give different results in this case.
    points = np.array([[9, 9], [0.5, 0.5], [10, 15], [0.4, 0.6]])
    # true centers are the unit vectors on lines y=x and y=1.5x
    true_centers = np.array([[0.70710678, 0.70710678], [0.5547002, 0.83205029]])
    kmeans = KMeans(2,
                    initial_clusters=kmeans_ops.RANDOM_INIT,
                    distance_metric=kmeans_ops.COSINE_DISTANCE,
                    use_mini_batch=self.use_mini_batch,
                    batch_size=4,
                    steps=30,
                    continue_training=True,
                    config=run_config.RunConfig(tf_random_seed=2),
                    random_seed=12)
    kmeans.fit(x=points)
    centers = normalize(kmeans.clusters())
    self.assertAllClose(np.sort(centers, axis=0),
                        np.sort(true_centers, axis=0))

  def test_transform_with_cosine_distance(self):
    points = np.array([[2.5, 3.5], [2, 8], [3, 1], [3, 18],
                       [-2.5, -3.5], [-2, -8], [-3, -1], [-3, -18]])

    true_centers = [normalize(np.mean(normalize(points)[4:, :], axis=0,
                                      keepdims=True))[0],
                    normalize(np.mean(normalize(points)[0:4, :], axis=0,
                                      keepdims=True))[0]]

    kmeans = KMeans(2,
                    initial_clusters=kmeans_ops.RANDOM_INIT,
                    distance_metric=kmeans_ops.COSINE_DISTANCE,
                    use_mini_batch=self.use_mini_batch,
                    batch_size=8,
                    continue_training=True,
                    config=run_config.RunConfig(tf_random_seed=3))
    kmeans.fit(x=points, steps=30)

    centers = normalize(kmeans.clusters())
    self.assertAllClose(np.sort(centers, axis=0),
                        np.sort(true_centers, axis=0),
                        atol=1e-2)

    true_transform = 1 - cosine_similarity(points, centers)
    transform = kmeans.transform(points)
    self.assertAllClose(transform, true_transform, atol=1e-3)

  def test_predict_with_cosine_distance(self):
    points = np.array([[2.5, 3.5], [2, 8], [3, 1], [3, 18],
                       [-2.5, -3.5], [-2, -8], [-3, -1], [-3, -18]]).astype(
                           np.float32)
    true_centers = np.array(
        [normalize(np.mean(normalize(points)[0:4, :],
                           axis=0,
                           keepdims=True))[0],
         normalize(np.mean(normalize(points)[4:, :],
                           axis=0,
                           keepdims=True))[0]])
    true_assignments = [0] * 4 + [1] * 4
    true_score = len(points) - np.tensordot(normalize(points),
                                            true_centers[true_assignments])

    kmeans = KMeans(2,
                    initial_clusters=kmeans_ops.RANDOM_INIT,
                    distance_metric=kmeans_ops.COSINE_DISTANCE,
                    use_mini_batch=self.use_mini_batch,
                    batch_size=8,
                    continue_training=True,
                    config=run_config.RunConfig(tf_random_seed=3))
    kmeans.fit(x=points, steps=30)

    centers = normalize(kmeans.clusters())
    self.assertAllClose(np.sort(centers, axis=0),
                        np.sort(true_centers, axis=0), atol=1e-2)

    assignments = kmeans.predict(points)
    self.assertAllClose(centers[assignments],
                        true_centers[true_assignments], atol=1e-2)

    score = kmeans.score(points)
    self.assertAllClose(score, true_score, atol=1e-2)

  def test_predict_with_cosine_distance_and_kmeans_plus_plus(self):
    # Most points are concetrated near one center. KMeans++ is likely to find
    # the less populated centers.
    points = np.array([[2.5, 3.5], [2.5, 3.5], [-2, 3], [-2, 3], [-3, -3],
                       [-3.1, -3.2], [-2.8, -3.], [-2.9, -3.1], [-3., -3.1],
                       [-3., -3.1], [-3.2, -3.], [-3., -3.]]).astype(np.float32)
    true_centers = np.array(
        [normalize(np.mean(normalize(points)[0:2, :], axis=0,
                           keepdims=True))[0],
         normalize(np.mean(normalize(points)[2:4, :], axis=0,
                           keepdims=True))[0],
         normalize(np.mean(normalize(points)[4:, :], axis=0,
                           keepdims=True))[0]])
    true_assignments = [0] * 2 + [1] * 2 + [2] * 8
    true_score = len(points) - np.tensordot(normalize(points),
                                            true_centers[true_assignments])

    kmeans = KMeans(3,
                    initial_clusters=kmeans_ops.KMEANS_PLUS_PLUS_INIT,
                    distance_metric=kmeans_ops.COSINE_DISTANCE,
                    use_mini_batch=self.use_mini_batch,
                    batch_size=12,
                    continue_training=True,
                    config=run_config.RunConfig(tf_random_seed=3))
    kmeans.fit(x=points, steps=30)

    centers = normalize(kmeans.clusters())
    self.assertAllClose(sorted(centers.tolist()),
                        sorted(true_centers.tolist()),
                        atol=1e-2)

    assignments = kmeans.predict(points)
    self.assertAllClose(centers[assignments],
                        true_centers[true_assignments], atol=1e-2)

    score = kmeans.score(points)
    self.assertAllClose(score, true_score, atol=1e-2)

  def test_fit_raise_if_num_clusters_larger_than_num_points_random_init(self):
    points = np.array([[2.0, 3.0], [1.6, 8.2]])

    with self.assertRaisesOpError('less'):
      kmeans = KMeans(num_clusters=3, initial_clusters=kmeans_ops.RANDOM_INIT)
      kmeans.fit(x=points)

  def test_fit_raise_if_num_clusters_larger_than_num_points_kmeans_plus_plus(
      self):
    points = np.array([[2.0, 3.0], [1.6, 8.2]])

    with self.assertRaisesOpError(AssertionError):
      kmeans = KMeans(num_clusters=3,
                      initial_clusters=kmeans_ops.KMEANS_PLUS_PLUS_INIT)
      kmeans.fit(x=points)


class MiniBatchKMeansTest(KMeansTest):

  @property
  def batch_size(self):
    return 50

  @property
  def use_mini_batch(self):
    return True


if __name__ == '__main__':
  tf.test.main()
