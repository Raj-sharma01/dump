# Part 1 — First establish whether the NER pipeline itself works

Before generating more data, make a tiny controlled dataset.

Use maybe **20–50 examples manually**.

For example:

```text
톰 크루즈
톰 크루즈가 출연한 영화
톰 크루즈의 영화
톰 크루즈의 액션 영화
톰 크루즈가 출연한 액션 영화
크리스토퍼 놀란의 영화
크리스토퍼 놀란이 감독한 영화
넷플릭스 액션 영화
한국 액션 영화
2020년 액션 영화
```

Annotate them manually.

For:

```text
톰 크루즈의 액션 영화
```

your gold annotation should be:

```text
톰 크루즈 → CAST
액션 → GENRE
영화 → CONTENT_TYPE
```

assuming that's your intended schema.

Then train a model **only on these 20–50 examples**, intentionally.

You should be able to overfit them.

After training, test those exact same sentences.

You want:

```text
톰 크루즈의 액션 영화

톰 크루즈       CAST
액션             GENRE
영화             CONTENT_TYPE
```

### If it cannot learn even these examples

**STOP.**

Don't create more templates.

Don't use a Transformer.

The problem is probably in:

* annotation offsets
* training code
* tokenizer
* labels
* training configuration
* data conversion

A neural NER model should be capable of memorizing a tiny dataset like this.

This is your **sanity test #1**.

---

# Part 2 — Verify your annotations programmatically

For every generated example, run:

```python
for start, end, label in entities:
    print(
        repr(text[start:end]),
        label
    )
```

For:

```text
톰 크루즈의 액션 영화
```

you MUST get:

```text
'톰 크루즈' CAST
'액션' GENRE
'영화' CONTENT_TYPE
```

Not:

```text
'톰 크루즈의' CAST
```

Not:

```text
'톰 크루즈의 액션 영화' TITLE
```

Not:

```text
'톰 크루즈' CAST
'액션 영화' GENRE
```

unless that is deliberately how your schema works.

I'd actually add an assertion:

```python
for start, end, label in entities:
    span = text[start:end]

    assert span.strip() == span
    print(f"{span!r} -> {label}")
```

Then manually inspect a few hundred.

---

# Part 3 — Check the tokenizer

This is particularly important for Korean.

Run:

```python
nlp = spacy.load("ko_core_news_lg")

text = "톰 크루즈의 액션 영화"

doc = nlp.make_doc(text)

for token in doc:
    print(
        token.text,
        token.idx,
        token.idx + len(token.text)
    )
```

You want to understand exactly how spaCy tokenizes it.

Then check whether your entity boundaries correspond to token boundaries.

For example:

```text
톰
크루즈
의
액션
영화
```

If your annotation is:

```text
톰 크루즈 → CAST
```

then the tokenizer should make that span naturally representable.

Do this for:

* Korean titles
* Korean actors
* Korean directors
* English names inside Korean
* mixed Korean/English titles
* punctuation
* numbers/year

---

# Part 4 — Test whether your model can recognize known entities

Now divide your dictionaries.

Suppose:

```text
TRAIN dictionary:
A = entities used during training

TEST dictionary:
B = entities used during testing
```

Create three test sets.

### Test 1 — seen entities

```text
entities in A
```

### Test 2 — unseen entities

```text
entities in B - A
```

### Test 3 — completely controlled

Use a tiny set where you know everything.

Then measure separately.

You might discover:

```text
Seen entities       92%
Unseen entities     31%
```

That tells you something very different from:

```text
Seen entities       35%
Unseen entities     25%
```

The first means **generalization is the problem**.

The second means **your pipeline/data/training is probably broken**.

---

# Part 5 — Test templates independently from entities

This is the most important experiment for your particular system.

Create a matrix.

### Same entity, different Korean constructions

For example:

```text
톰 크루즈
톰 크루즈 영화
톰 크루즈 출연 영화
톰 크루즈가 출연한 영화
톰 크루즈가 나오는 영화
톰 크루즈의 영화
톰 크루즈 출연작
톰 크루즈가 나온 영화
톰 크루즈가 나오는 액션 영화
톰 크루즈의 액션 영화
```

Now evaluate each separately.

You may find:

| Pattern       | Result |
| ------------- | -----: |
| 톰 크루즈         |      ✅ |
| 톰 크루즈 영화      |      ✅ |
| 톰 크루즈 출연 영화   |      ✅ |
| 톰 크루즈가 출연한 영화 |      ✅ |
| 톰 크루즈가 나오는 영화 |      ❌ |
| 톰 크루즈의 영화     |      ❌ |
| 톰 크루즈의 액션 영화  |      ❌ |

If so, **you've identified a template coverage problem**, not a model architecture problem.

---

# Part 6 — Do the same for every entity type

Build a test matrix:

```text
CAST
DIRECTOR
TITLE
GENRE
CONTENT_TYPE
STREAMING_APP
YEAR
```

And for each entity, test:

```text
entity alone
entity + noun
entity + particle
entity + verb
entity + another entity
entity at beginning
entity in middle
entity at end
```

For example:

### CAST

```text
톰 크루즈
톰 크루즈 영화
톰 크루즈 출연 영화
톰 크루즈가 출연한 영화
톰 크루즈가 나오는 영화
톰 크루즈의 영화
톰 크루즈가 출연한 액션 영화
톰 크루즈의 액션 영화
```

### DIRECTOR

```text
크리스토퍼 놀란 영화
크리스토퍼 놀란 감독 영화
크리스토퍼 놀란이 감독한 영화
크리스토퍼 놀란의 영화
크리스토퍼 놀란 작품
크리스토퍼 놀란이 만든 영화
```

### GENRE

```text
액션 영화
액션 장르 영화
액션 영화 추천
액션 장르의 영화
액션이 들어간 영화
액션 영화 중에서
```

This gives you a **linguistic coverage test**.

---

# Part 7 — Check whether TITLE is swallowing everything

Your specific failure:

```text
톰 크루즈의 액션 영화
^^^^^^^^^^^^^^^^^^^^^^^^
TITLE
```

makes me particularly interested in your TITLE training data.

Calculate something like:

```text
TITLE examples:
{TITLE} 영화
{TITLE} 같은 영화
{TITLE} 추천
{TITLE} 액션 영화
{TITLE}의 영화
...
```

If your training data frequently contains patterns where **long noun phrases are TITLE**, the model may have learned a very strong TITLE boundary.

I'd inspect:

> What tokens occur immediately before and after TITLE?

and compare that against CAST/GENRE/CONTENT_TYPE.

---

# Part 8 — Check label ambiguity

Create this mapping:

```python
surface_form -> labels
```

For example:

```text
영화 → CONTENT_TYPE
액션 → GENRE
넷플릭스 → STREAMING_APP
톰 크루즈 → CAST
```

Good.

But if you find:

```text
영화 → {TITLE, CONTENT_TYPE}
액션 → {TITLE, GENRE}
```

frequently, that's a problem.

Especially with your synthetic data.

If the same exact dictionary value appears as different labels, you need to know **why**.

---

# Part 9 — Measure entity-level performance

Get:

```text
TITLE
CAST
GENRE
CONTENT_TYPE
APP
YEAR
```

separately.

For example:

| Entity       | Precision | Recall | F1 |
| ------------ | --------: | -----: | -: |
| TITLE        |        20 |     30 | 24 |
| CAST         |        70 |     65 | 67 |
| DIRECTOR     |        72 |     60 | 65 |
| GENRE        |        50 |     55 | 52 |
| CONTENT_TYPE |        40 |     45 | 42 |

Then we'd know:

> TITLE is destroying the overall score.

That is much more actionable.

---

# CAST templates

```text
{CAST}
{CAST} 영화
{CAST} 출연 영화
{CAST}가 출연한 영화
{CAST}이 출연한 영화
{CAST}가 나오는 영화
{CAST}이 나오는 영화
{CAST}가 나온 영화
{CAST}이 나온 영화
{CAST} 출연작
{CAST}의 영화
{CAST}가 출연한 작품
{CAST}이 출연한 작품
{CAST}가 나오는 작품
{CAST}의 출연작
{CAST} 출연 영화 추천
{CAST}가 출연한 영화 추천
{CAST}가 나오는 액션 영화
{CAST}의 액션 영화
{CAST}가 출연한 {GENRE} 영화
{CAST}가 나오는 {GENRE} 영화
```

**Important:** Don't blindly use both `가` and `이` after every name.

Your template system should know whether the preceding Korean syllable takes 받침.

For example:

```text
톰 크루즈 + 가
```

is natural, while other names may require `이`.

So ideally your generator should have a small Korean particle-selection function rather than randomly attaching `이/가`.

---

# GENRE templates

```text
{GENRE} 영화
{GENRE} 영화 추천
{GENRE} 장르 영화
{GENRE} 장르의 영화
{GENRE} 영화 찾아줘
{GENRE} 영화 보여줘
{GENRE} 영화 추천해줘
{GENRE} 영화 중에서
{GENRE} 장르 중에서
{GENRE}인 영화
{GENRE} 같은 영화
{GENRE} 요소가 있는 영화
{GENRE} 영화 추천 목록
{GENRE} 영화 뭐가 있어
{GENRE} 영화 알려줘
```

---

# CONTENT_TYPE templates

Assuming values such as:

```text
영화
드라마
시리즈
애니메이션
다큐멘터리
```

use:

```text
{CONTENT_TYPE}
{CONTENT_TYPE} 추천
{CONTENT_TYPE} 찾아줘
{CONTENT_TYPE} 보여줘
{CONTENT_TYPE} 보고 싶어
좋은 {CONTENT_TYPE} 추천해줘
{CONTENT_TYPE} 뭐가 있어
{CONTENT_TYPE} 알려줘
{CONTENT_TYPE} 중에서 추천
{CONTENT_TYPE} 목록
재미있는 {CONTENT_TYPE}
최근 {CONTENT_TYPE}
인기 {CONTENT_TYPE}
```

---

# TITLE templates

This one needs **much more variation** because TITLE is probably your dominant entity.

```text
{TITLE}
{TITLE} 찾아줘
{TITLE} 보여줘
{TITLE} 보고 싶어
{TITLE} 보고 싶다
{TITLE} 추천해줘
{TITLE} 같은 영화
{TITLE} 비슷한 영화
{TITLE}와 비슷한 영화
{TITLE} 같은 작품
{TITLE}의 비슷한 영화
{TITLE} 영화
{TITLE} 정보
{TITLE} 출연진
{TITLE} 배우
{TITLE} 감독
{TITLE} 줄거리
{TITLE} 내용
```

But be careful:

```text
{TITLE} 영화
```

can make your model learn that the following `영화` is somehow part of the title context.

That's okay if your annotation is:

```text
{TITLE} → TITLE
영화 → CONTENT_TYPE
```

but you need **lots of such examples**.

---

# Combined templates — these are VERY important

Your actual system isn't single-entity NER.

It's multi-entity query understanding.

So you need combinations.

### CAST + GENRE + CONTENT_TYPE

```text
{CAST}의 {GENRE} {CONTENT_TYPE}
{CAST}가 출연한 {GENRE} {CONTENT_TYPE}
{CAST}가 나오는 {GENRE} {CONTENT_TYPE}
{CAST} 출연 {GENRE} {CONTENT_TYPE}
{GENRE} {CONTENT_TYPE} 중 {CAST}가 출연한 것
{CAST}가 나온 {GENRE} {CONTENT_TYPE} 추천
{CAST}의 {GENRE} 작품
```

This directly gives you:

```text
톰 크루즈의 액션 영화
```

with:

```text
톰 크루즈 → CAST
액션 → GENRE
영화 → CONTENT_TYPE
```


---

### TITLE + CAST

```text
{TITLE}에 나온 {CAST}
{TITLE}에 출연한 {CAST}
{TITLE}의 {CAST}
{TITLE} 출연 배우 {CAST}
{TITLE}에 {CAST}가 나와?
{CAST}가 {TITLE}에 나오는지
```

---

### TITLE + GENRE

```text
{TITLE}와 비슷한 {GENRE} 영화
{TITLE} 같은 {GENRE} 영화
{TITLE}와 비슷한 {GENRE} 작품
{TITLE}의 장르
{TITLE}와 같은 장르의 영화
```

---

# And don't forget search-style Korean

This is extremely important for your application.

Add intentionally **unnatural/incomplete search queries**:

```text
톰 크루즈 액션 영화
톰 크루즈 영화
톰 크루즈 출연작
톰 크루즈 나오는 영화
크리스토퍼 놀란 영화
놀란 감독 영화
넷플릭스 액션
넷플릭스 액션 영화
한국 액션 영화
2020년 이후 액션
2020년 이후 영화
톰 크루즈 넷플릭스 영화
톰 크루즈 액션 넷플릭스
놀란 2010년 이후 영화
```

These may actually be **more important than grammatically perfect Korean** for your search engine.

---
