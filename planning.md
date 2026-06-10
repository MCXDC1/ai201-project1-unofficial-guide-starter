# Project 1 Planning: The Unofficial Guide

> Write this document before you write any pipeline code.
> Your spec and architecture diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Update the Retrieval Approach and Chunking Strategy sections if you change your approach during implementation.
> Update this file before starting any stretch features.

---

## Domain

I chose to do the a review of the engineering department at a university. This is difficult to get through official channels as most universities do not present information on which professors are better than others and which classes go well together or should be taken in different semesters. Using information across online sources you can find an honest opinion on courses, professors, and coursework of the engineering department. It will also focus on the community surrounding the majors.

---

## Documents

<!-- List your specific sources: URLs, subreddit names, forum threads, or file descriptions.
     Aim for at least 10 sources that together cover different subtopics or perspectives within your domain. -->

| # | Source | Description | URL or location |
|---|--------|-------------|-----------------|
| 1 | USNEWS| General information about the engineering department. Rankings across US. | https://www.usnews.com/best-graduate-schools/top-engineering-schools/university-of-connecticut-02036 |
| 2 | Reddit| Student discussion on academic pressure in department| https://www.reddit.com/r/UCONN/comments/1blyp5m/how_hard_is_engineering_academic_pressure_and/ |
| 3 | Reddit | Student discussion on engineering professors | https://www.reddit.com/r/UCONN/comments/1f1t50k/how_are_the_engineering_professors_at_uconn/ |
| 4 | Quora| Review on CS department at university| https://www.quora.com/How-is-the-Computer-Science-Department-at-UCONN|
| 5 |Reddit | Student discussion on women in engineering communities  | https://www.reddit.com/r/UCONN/comments/12yw9mn/choosing_an_engineering_lc/|
| 6 | UCONN | Official information on engineering oppurtunities| https://advising.engineering.uconn.edu/support-opportunities/engineering-experiential-education/ |
| 7 | RateMyProfessor| Ranking of every engineering professor | https://www.ratemyprofessors.com/search/professors/1091?q=*&did=17 |
| 8 | UCONN| Information about the female population in engineering| https://today.uconn.edu/2021/10/uconn-engineering-records-largest-female-freshman-class-at-storrs-in-history/ |
| 9 | UCONN | Information on UCONN's lead in female engineers| https://today.uconn.edu/2019/11/uconn-national-leader-educating-women-engineers/|
| 10 | UCONN | General requirements for engineers in department| https://catalog.uconn.edu/undergraduate/engineering/#requirementstext |

---

## Chunking Strategy


<!-- How will you split documents into chunks?
     State your chunk size (in tokens or characters), overlap size, and explain why those
     numbers fit the structure of your documents.
     A review-heavy corpus warrants different chunking than a long FAQ. -->

     When researching the best way to split documents that vary, I think that I will need to scan my sources before I decide how I will split it. The reddit comments will need to be split different compared to my articles.

**Chunk size:**
Reddit/Quora?Ratings: One chunk per comment/review

**Overlap:**
Will matter with articles, not with rate my professor or reddit comments

**Reasoning:**

Ratings/reviews are easier to split and individually understand but the news will need context

---

## Retrieval Approach

<!-- Which embedding model are you using (e.g., all-MiniLM-L6-v2 via sentence-transformers)?
     How many chunks will you retrieve per query (top-k)?
     If you were deploying this for real users and cost wasn't a constraint, what tradeoffs
     would you weigh in choosing a different embedding model — context length, multilingual
     support, accuracy on domain-specific text, latency? -->

**Embedding model:**
all-MiniLM-L6-v2 via sentence-transformers

**Top-k:**
5

**Production tradeoff reflection:**
I would be able to value different opinions higher, where a student on reddit saying one thing about a professor could be debated by an article specifically detailing how great one professor is, maybe more accuracy when comparing. I would also extend context length within reviews as responses to other reviews could provide context that gets lost.

---

## Evaluation Plan

<!-- List your 5 test questions with their expected correct answers.
     Questions should be specific enough that you can judge whether the system's response
     is right or wrong. "What are good dining halls?" is too vague.
     "What do students say about wait times at [dining hall name] during lunch?" is testable. -->

| # | Question | Expected answer |
|---|----------|-----------------|
| 1 | Is UCONN's engineering academically rigorous? | It is comparably average to other universities, but can be hard to catch back up if you fall behind in earlier years|
| 2 | Is there a good female community in UCONN's college of engineering? | Sources say that the population of females in engineering has gone up with leadership positions being heavily pursued by female engineers.|
| 3 | What community should I join as a female engineer at UCONN? | The Engineering LC seems to be have more oppurtunities and more time spent on its students.|
| 4 | Is the graduate program good for CS majors at UCONN?| Yes, it provides research oppurtunities and funding.|
| 5 | Does UCONN's engineering department compare to other universities?| It is above average in comparison to most public universiites in the US.|

---

## Anticipated Challenges

<!-- What could go wrong? Name at least two specific risks with reasoning.
     Consider: noisy or inconsistent documents, missing source attribution, off-topic
     retrieval, chunks that split key information across boundaries. -->

1. The rate my professor has a lot of information but the entire page needs to load which might not keep all of it.

2. The reddit/ quora forum could have comments that get have untrue/outdated information.

---

## Architecture

<!-- Draw a diagram of your pipeline showing the five stages:
     Document Ingestion → Chunking → Embedding + Vector Store → Retrieval → Generation
     Label each stage with the tool or library you're using.
     You can use ASCII art, a Mermaid diagram, or embed a sketch as an image.
     You'll use this diagram as context when prompting AI tools to implement each stage. -->

---

## AI Tool Plan

<!-- For each part of the pipeline below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, which requirements)
     - What you expect it to produce
     - How you'll verify the output matches your spec

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Chunking Strategy section and ask it to implement chunk_text()
     with my specified chunk size and overlap" is a plan. -->

**Milestone 3 — Ingestion and chunking:**
Claude
I will give it the websites I plan to use and see how I should go about chunking the different sources. It will most likely explain what each website will need from me. I will go to each website and make sure I am retrieving the right information.

**Milestone 4 — Embedding and retrieval:**
Claude
I will use my test questions and see how it is comparing.

**Milestone 5 — Generation and interface:**
Claude
I will use my test questions and see if it provides accurate sources and is using the info from my websites.