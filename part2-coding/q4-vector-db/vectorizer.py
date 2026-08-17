# turns a piece of text into a fixed size vector, without sentence-transformers
# or any embedding api. everything here is standard library.
#
# how it works ("hashing trick"):
#   1. cut the text into features - whole words AND 3 letter chunks
#   2. hash every feature into a bucket number between 0 and DIM-1
#   3. count how often each bucket gets hit
#   4. normalize the result to length 1
#
# the 3 letter chunks are the important bit. with only whole words "hamburger"
# and "cheeseburger" share nothing at all, but as chunks they both contain
# bur/urg/rge/ger so they come out similar. that's the closest i can get to
# "understanding" without a real model.
#
# to be clear about the limits: this matches SPELLING, not meaning. it will
# never work out that "fries" and "potato" are related, a real embedding model
# would. for question 4 that's ok because the point is the similarity maths,
# not the embedding quality.

import re
import hashlib

DIM = 256


def _bucket(feature):
    # NOTE: python's built-in hash() is randomised every time the process
    # starts (PYTHONHASHSEED), so the same word would land in a different
    # bucket on the next run and everything already stored in the database
    # would be garbage. md5 is stable forever, which is what we need here.
    digest = hashlib.md5(feature.encode("utf-8")).digest()
    number = int.from_bytes(digest[:8], "big")

    bucket = number % DIM
    # use one spare bit to decide whether to add or subtract. when two
    # different features land in the same bucket this makes them cancel out
    # instead of piling up and faking a strong match.
    sign = 1 if (number >> 63) & 1 else -1
    return bucket, sign


def features(text):
    text = text.lower()
    words = re.findall(r"[a-z0-9]+", text)

    out = []
    for word in words:
        out.append("w:" + word)

        # pad short words so a 2 letter word still produces something
        padded = "^" + word + "$"
        for i in range(len(padded) - 2):
            out.append("c:" + padded[i:i + 3])
    return out


def vectorize(text):
    vec = [0.0] * DIM

    for feature in features(text):
        bucket, sign = _bucket(feature)
        vec[bucket] += sign

    # normalize to length 1. two reasons: cosine ignores length anyway so we
    # may as well do the division once here instead of on every comparison,
    # and it stops long text automatically beating short text.
    total = 0.0
    for x in vec:
        total += x * x

    if total == 0.0:
        return vec          # empty string, nothing we can do

    length = total ** 0.5
    return [x / length for x in vec]


if __name__ == "__main__":
    # quick sanity check by hand
    from cosine import cosine_similarity

    pairs = [
        ("hamburger", "cheeseburger"),
        ("hamburger", "burger"),
        ("hamburger", "hamburgers"),
        ("hamburger", "iced lemon tea"),
        ("fried chicken", "chicken wings"),
    ]
    for a, b in pairs:
        score = cosine_similarity(vectorize(a), vectorize(b))
        print("%-16s vs %-16s  %.4f" % (a, b, score))
