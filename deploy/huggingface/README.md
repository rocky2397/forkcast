---
title: Forkcast
emoji: 🍳
colorFrom: red
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: other
short_description: What should I cook next? Try it with a demo kitchen.
---

# Forkcast demo

Forkcast suggests what to cook from what's in your kitchen, learns your taste
from the dishes you cook, and puts recipes that fit your day's calories and
macros first.

This is a public demo. You get your own copy of a demo kitchen with a few
ingredients, a profile and two dishes already cooked. Add or remove
ingredients, cook something, rate it, and watch the recipe list change. Your
changes are private to you and saved for your browser, so they are still there
when you come back. They are deleted 30 days after your last visit, or at once
with "Delete my data" in the banner. What is saved is the kitchen, your meals
and the profile, under a random id only your browser knows: no name, email or
IP address.

You can photograph your groceries or a nutrition label: the photo is sent to
Anthropic's Claude to be read and Forkcast doesn't keep it. Up to 10 scans a
day per visitor, and you always confirm what was read before anything is
saved.

Usage is counted only as anonymous totals (no IP addresses, nothing typed,
nothing per visitor). They are public at `/stats` on the app.

Code, evaluation and design notes: https://github.com/rocky2397/forkcast

The code is MIT-licensed. The recipes come from the public food.com dataset
and are shown for non-commercial demo use only; the ingredient embeddings are
Epicure (KAIKAKU.AI, CC BY 4.0). Details are in the project README.
