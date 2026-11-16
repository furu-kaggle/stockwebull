"""Classify X posts by what they point at, using hand labels as the model's examples.

  event     reports a specific real incident or vulnerability
  reaction  comments on / jokes about a specific real incident or a named company's failure
  vibe      security as a theme with no specific incident behind it (general jokes, advice, predictions)
  offtopic  security words in another context (politics, conspiracy, war claims, promotions)

Labels in draft/x_labels/labels_*.csv were assigned by reading each post. A text classifier trained on
them labels the rest; its accuracy on held-out labelled posts is printed. Output: draft/x_kinds.csv.

Usage: python draft/x_classify.py
"""
import glob
import os

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline

from x_sentiment import POSTS, is_relevant

HERE = os.path.dirname(os.path.abspath(__file__))
KINDS = ["event", "reaction", "vibe", "offtopic"]


def load_posts():
    posts = pd.read_csv(POSTS, dtype={"id": str})
    posts = posts[posts["id"].notna()].copy()
    posts = posts.drop_duplicates("id")
    posts = posts[posts["text"].map(is_relevant)]
    posts["doc"] = posts["text"].fillna("") + " ||| " + posts["bio"].fillna("").map(lambda b: " ".join("bio_" + w for w in str(b).lower().split()[:25]))
    return posts


def main():
    posts = load_posts()
    # The labelling batches carry rounded ids, so labels are matched back to posts by author and text.
    parts = []
    for path in sorted(glob.glob(os.path.join(HERE, "x_labels", "labels_*.csv"))):
        batch = pd.read_csv(path.replace("labels_", "batch_"), dtype=str)[["id", "user", "text"]]
        parts.append(batch.merge(pd.read_csv(path, dtype=str), on="id")[["user", "text", "kind"]])
    labels = pd.concat(parts)
    labels = labels[labels["kind"].isin(KINDS)].drop_duplicates(["user", "text"])
    train = posts.merge(labels, on=["user", "text"])
    print(f"{len(posts)} relevant posts, {len(train)} hand-labelled ({len(labels) - len(train)} labels did not match a post)")
    print("hand labels:", train["kind"].value_counts().to_dict(), "\n")

    model = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
                          LogisticRegression(C=8, max_iter=2000, class_weight="balanced"))
    held_out = cross_val_predict(model, train["doc"], train["kind"], cv=StratifiedKFold(5, shuffle=True, random_state=0))
    print(f"accuracy on held-out labelled posts: {(held_out == train['kind']).mean():.0%}")
    print(classification_report(train["kind"], held_out, labels=KINDS, digits=2, zero_division=0))
    print("how held-out posts were confused (rows = true kind, columns = predicted):")
    print(pd.crosstab(train["kind"], pd.Series(held_out, index=train.index, name="predicted")).reindex(index=KINDS, columns=KINDS, fill_value=0).to_string(), "\n")

    model.fit(train["doc"], train["kind"])
    rest = posts[~posts["id"].isin(train["id"])]
    proba = model.predict_proba(rest["doc"])
    predicted = pd.DataFrame({"id": rest["id"].values, "kind": model.classes_[proba.argmax(axis=1)], "source": "model",
                              "confidence": proba.max(axis=1).round(2)})
    hand = pd.DataFrame({"id": train["id"].values, "kind": train["kind"].values, "source": "hand", "confidence": 1.0})
    kinds = pd.concat([hand, predicted], ignore_index=True)
    kinds.to_csv(os.path.join(HERE, "x_kinds.csv"), index=False)
    print("all posts:", kinds["kind"].value_counts().to_dict(), "| by model:", int((kinds.source == "model").sum()),
          f"| model confidence below 50%: {int(((kinds.source == 'model') & (kinds.confidence < 0.5)).sum())}")


if __name__ == "__main__":
    main()
