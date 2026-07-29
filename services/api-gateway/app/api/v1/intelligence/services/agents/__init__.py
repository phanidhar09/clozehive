"""Tool-calling agents.

Unlike the rest of the AI stack (fixed pipelines that decide what to fetch before
the model runs), agents let the model choose its own lookups. Reserved for
questions where the next lookup depends on the previous answer.

:mod:`loop` is the shared harness; one module per agent alongside it.
"""
