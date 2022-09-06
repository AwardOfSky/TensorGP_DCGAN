# -*- coding: utf-8 -*-
"""dcgan.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/github/tensorflow/docs/blob/master/site/en/tutorials/generative/dcgan.ipynb

##### Copyright 2019 The TensorFlow Authors.
"""

#@title Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Adapted from https://www.tensorflow.org/tutorials/generative/dcgan
import csv

import pylab
import tensorflow as tf

tf.__version__

# To generate GIFs
#!pip install imageio
#!pip install git+https://github.com/tensorflow/docs

#import glob
#import imageio
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import os
import PIL
from tensorflow.keras import layers
import time
import sys
import datetime
from keras.models import load_model

delimiter = os.path.sep
cnn_model = load_model('MNIST_keras_CNN.h5')

gen_image_cnt = 0
fake_image_cnt = 0

#from IPython import display

"""### Load and prepare the dataset

You will use the MNIST dataset to train the generator and the discriminator.
The generator will generate handwritten digits resembling the MNIST data.
"""

(train_images, train_labels), (_, _) = tf.keras.datasets.mnist.load_data()
digits_to_train = [0]
if len(sys.argv) > 1:
    print("going for digit: ", sys.argv[1])
    digits_to_train = [int(sys.argv[1])]

train_mask = np.isin(train_labels, digits_to_train)
train_images = train_images[train_mask]
print("Length of dataset: ", len(train_images))
train_images = train_images.reshape(train_images.shape[0], 28, 28, 1).astype('float32')
train_images = (train_images - 127.5) / 127.5  # Normalize the images to [-1, 1]
#train_images = train_images[:64] # testing purposes

BUFFER_SIZE = 60000
BATCH_SIZE = 32

# Batch and shuffle the data
train_dataset = tf.data.Dataset.from_tensor_slices(train_images).shuffle(len(train_images)).batch(BATCH_SIZE)


#paths

temp = sys.argv[2] if len(sys.argv) > 2 else ""
pref = datetime.datetime.utcnow().strftime('%Y_%m_%d__%H_%M_%S_%f')[:-3] + "_" + temp
# print(date)
run_dir = os.getcwd() + delimiter + "gp_dcgan_results" + delimiter + "run__" + pref + delimiter
gan_images = run_dir + "dcgan_images" + delimiter
os.makedirs(gan_images)
loss_hist = []

"""## Create the models
Both the generator and discriminator are defined using the [Keras Sequential API
(https://www.tensorflow.org/guide/keras#sequential_model).

### The Generator
The generator uses `tf.keras.layers.Conv2DTranspose` (upsampling) layers to produce an image from a seed (random noise).
Start with a `Dense` layer that takes this seed as input,
then upsample several times until you reach the desired image size of 28x28x1.
Notice the `tf.keras.layers.LeakyReLU` activation for each layer, except the output layer which uses tanh.
"""

def make_generator_model():
    model = tf.keras.Sequential()
    model.add(layers.Dense(7*7*256, use_bias=False, input_shape=(100,)))
    model.add(layers.BatchNormalization())
    model.add(layers.LeakyReLU())

    model.add(layers.Reshape((7, 7, 256)))
    assert model.output_shape == (None, 7, 7, 256)  # Note: None is the batch size

    model.add(layers.Conv2DTranspose(128, (5, 5), strides=(1, 1), padding='same', use_bias=False))
    assert model.output_shape == (None, 7, 7, 128)
    model.add(layers.BatchNormalization())
    model.add(layers.LeakyReLU())

    model.add(layers.Conv2DTranspose(64, (5, 5), strides=(2, 2), padding='same', use_bias=False))
    assert model.output_shape == (None, 14, 14, 64)
    model.add(layers.BatchNormalization())
    model.add(layers.LeakyReLU())

    model.add(layers.Conv2DTranspose(1, (5, 5), strides=(2, 2), padding='same', use_bias=False, activation='tanh'))
    assert model.output_shape == (None, 28, 28, 1)

    return model

"""Use the (as yet untrained) generator to create an image."""

generator = make_generator_model()
#generator.summary()


noise = tf.random.normal([1, 100])
generated_image = generator(noise, training=False)

#plt.imshow(generated_image[0, :, :, 0], cmap='gray')

"""### The Discriminator

The discriminator is a CNN-based image classifier.
"""

def make_discriminator_model():
    model = tf.keras.Sequential()
    model.add(layers.Conv2D(64, (5, 5), strides=(2, 2), padding='same',
                                     input_shape=[28, 28, 1]))
    model.add(layers.LeakyReLU())
    model.add(layers.Dropout(0.3))

    model.add(layers.Conv2D(128, (5, 5), strides=(2, 2), padding='same'))
    model.add(layers.LeakyReLU())
    model.add(layers.Dropout(0.3))

    model.add(layers.Flatten())
    model.add(layers.Dense(1))

    return model

"""Use the (as yet untrained) discriminator to classify the generated images as real or fake.
The model will be trained to output positive values for real images, and negative values for fake images."""

discriminator = make_discriminator_model()
decision = discriminator(generated_image)
#print(discriminator.summary())
#exit()

"""## Define the loss and optimizers
Define loss functions and optimizers for both models.
"""

# This method returns a helper function to compute cross entropy loss
cross_entropy = tf.keras.losses.BinaryCrossentropy(from_logits=True)

"""### Discriminator loss
This method quantifies how well the discriminator is able to distinguish real images from fakes.
It compares the discriminator's predictions on real images to an array of 1s,
and the discriminator's predictions on fake (generated) images to an array of 0s.
"""

def discriminator_loss(real_output, fake_output):
    real_loss = cross_entropy(tf.ones_like(real_output), real_output)
    fake_loss = cross_entropy(tf.zeros_like(fake_output), fake_output)
    total_loss = real_loss + fake_loss
    return total_loss

"""### Generator loss
The generator's loss quantifies how well it was able to trick the discriminator.
Intuitively, if the generator is performing well, the discriminator will classify the fake images as real (or 1).
Here, compare the discriminators decisions on the generated images to an array of 1s.
"""

def generator_loss(fake_output):
    return cross_entropy(tf.ones_like(fake_output), fake_output)

"""The discriminator and the generator optimizers are different since you will train two networks separately."""

generator_optimizer = tf.keras.optimizers.Adam(1e-4)
discriminator_optimizer = tf.keras.optimizers.Adam(1e-4)

"""### Save checkpoints
This notebook also demonstrates how to save and restore models,
which can be helpful in case a long running training task is interrupted.
"""

checkpoint_dir = './training_checkpoints'
checkpoint_prefix = os.path.join(checkpoint_dir, "ckpt")
checkpoint = tf.train.Checkpoint(generator_optimizer=generator_optimizer,
                                 discriminator_optimizer=discriminator_optimizer,
                                 generator=generator,
                                 discriminator=discriminator)

"""## Define the training loop

"""

EPOCHS = 5
noise_dim = 100
num_examples_to_generate = 32

# You will reuse this seed overtime (so it's easier)
# to visualize progress in the animated GIF)
seed = tf.random.normal([num_examples_to_generate, noise_dim])

"""The training loop begins with generator receiving a random seed as input. That seed is used to produce an image.
The discriminator is then used to classify real images (drawn from the training set)
and fakes images (produced by the generator).
The loss is calculated for each of these models, and the gradients are used to update the generator and discriminator."""

# Notice the use of `tf.function`
# This annotation causes the function to be "compiled".
#@tf.function
def train_step(images):
    global gen_image_cnt, fake_image_cnt
    noise = tf.random.normal([BATCH_SIZE, noise_dim])
    gen_image_cnt += BATCH_SIZE
    fake_image_cnt += len(images)
    #print("len images, ", len(images))

    with tf.GradientTape() as gen_tape, tf.GradientTape() as disc_tape:
      generated_images = generator(noise, training=True)

      real_output = discriminator(images, training=True)
      fake_output = discriminator(generated_images, training=True)

      gen_loss = generator_loss(fake_output)
      disc_loss = discriminator_loss(real_output, fake_output)

    gradients_of_generator = gen_tape.gradient(gen_loss, generator.trainable_variables)
    gradients_of_discriminator = disc_tape.gradient(disc_loss, discriminator.trainable_variables)

    generator_optimizer.apply_gradients(zip(gradients_of_generator, generator.trainable_variables))
    discriminator_optimizer.apply_gradients(zip(gradients_of_discriminator, discriminator.trainable_variables))
    loss_hist.append([disc_loss.numpy(), gen_loss.numpy()])

def train(dataset, epochs):
  s = 0
  for epoch in range(epochs):
      start = time.time()

      step = 0
      for image_batch in dataset:
          train_step(image_batch)
          fn = run_dir + "gan_losses.txt"
          with open(fn, mode='a', newline='') as file:
              fwriter = csv.writer(file, delimiter=',')
              if s == 0:
                  file.write("[d_loss, g_loss]\n")
              fwriter.writerow(loss_hist[-1])
              print('[DCGAN - step {}/{} of epoch {}/{}]:\tTime so far: {} sec'.format(step + 1, len(dataset), epoch + 1, epochs, time.time() - start))

          s += 1
          step += 1

      # Produce images for the GIF as you go
      #display.clear_output(wait=True)
      #generate_and_save_images(generator, epoch + 1, seed)

      # Save the model every 15 epochs
      if (epoch + 1) % 15 == 0:
          checkpoint.save(file_prefix = checkpoint_prefix)

      print('Time for epoch {} is {} sec'.format(epoch + 1, time.time()-start))

  # Generate after the final epoch
  #display.clear_output(wait=True)
  #generate_and_save_images(generator, epochs, seed)

"""**Generate and save images**

"""

def generate_and_save_images(model, epoch, test_input):
  # Notice `training` is set to False.
  # This is so all layers run in inference mode (batchnorm).
  predictions = model(test_input, training=False)

  fn = gan_images + "digit_max.txt"

  with open(fn, mode='a', newline='') as file:
      fwriter = csv.writer(file, delimiter=',')
      if epoch == 1:
          file.write("[epoch, max]\n")
      temp_list = np.argmax(classify_digits(predictions), axis=1)
      #print(temp_list)
      freq = np.count_nonzero(temp_list == digits_to_train[0]) / len(temp_list)
      #print(freq)
      fwriter.writerow([epoch] + list(temp_list) + [freq])

  fig = plt.figure(figsize=(8, 4))
  for i in range(predictions.shape[0]):
      plt.subplot(4, 8, i + 1)
      plt.imshow(predictions[i, :, :, 0] * 127.5 + 127.5, cmap='gray')
      plt.axis('off')

  plt.savefig(gan_images + 'image_at_epoch_{:04d}.png'.format(epoch))
  #plt.show()
  plt.close()


def plot_losses(show_graphics=False):
    fig, ax = plt.subplots(1, 1)
    ax.plot(range(len(loss_hist)), np.asarray(loss_hist)[:, 0], linestyle='-', label="D loss")
    pylab.legend(loc='upper left')
    ax.set_xlabel('Training steps')
    ax.set_ylabel('Loss')
    ax.get_xaxis().set_major_formatter(mticker.ScalarFormatter())
    ax.get_yaxis().set_major_formatter(mticker.ScalarFormatter())
    ax.set_title('Discriminator loss across training steps')
    fig.set_size_inches(12, 8)
    plt.savefig(fname=run_dir + 'Losses.svg', format="svg")
    if show_graphics: plt.show()
    plt.close(fig)


def classify_digits(digits):
    return cnn_model(digits, training=False)



"""## Train the model
Call the `train()` method defined above to train the generator and discriminator simultaneously.
Note, training GANs can be tricky.
It's important that the generator and discriminator do not overpower each other
(e.g., that they train at a similar rate).

At the beginning of the training, the generated images look like random noise.
As training progresses, the generated digits will look increasingly real.
After about 50 epochs, they resemble MNIST digits. This may take about one minute / epoch with the default settings on Colab.
"""

start = time.time()
train(train_dataset, EPOCHS)
plot_losses()
print('Time for all epochs is {} sec'.format(time.time()-start))
print("Number of gen image: ", gen_image_cnt)
print("Number of fake images: ", fake_image_cnt)

"""Restore the latest checkpoint."""

checkpoint.restore(tf.train.latest_checkpoint(checkpoint_dir))

"""## Create a GIF
"""

# Display a single image using the epoch number
#def display_image(epoch_no):
#  return PIL.Image.open('image_at_epoch_{:04d}.png'.format(epoch_no))

#display_image(EPOCHS)

"""Use `imageio` to create an animated gif using the images saved during training."""
"""
anim_file = 'dcgan.gif'

with imageio.get_writer(anim_file, mode='I') as writer:
  filenames = glob.glob('image*.png')
  filenames = sorted(filenames)
  for filename in filenames:
    image = imageio.imread(filename)
    writer.append_data(image)
  image = imageio.imread(filename)
  writer.append_data(image)

import tensorflow_docs.vis.embed as embed
embed.embed_file(anim_file)
"""
"""## Next steps

This tutorial has shown the complete code necessary to write and train a GAN. As a next step, you might like to experiment with a different dataset, for example the Large-scale Celeb Faces Attributes (CelebA) dataset [available on Kaggle](https://www.kaggle.com/jessicali9530/celeba-dataset). To learn more about GANs see the [NIPS 2016 Tutorial: Generative Adversarial Networks](https://arxiv.org/abs/1701.00160).
"""