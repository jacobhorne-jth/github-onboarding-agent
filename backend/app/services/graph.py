from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END

class State(TypedDict):
    namespace: str
    question: str
    hits: List[Dict[str, Any]]
    answer: str

def build_graph(retriever_fn, answer_fn):
    g = StateGraph(State)

    def retrieve_node(state: State):
        hits = retriever_fn(state["namespace"], state["question"])
        return {"hits": hits}

    def answer_node(state: State):
        answer = answer_fn(state["question"], state["hits"])
        return {"answer": answer}

    g.add_node("retrieve", retrieve_node)
    g.add_node("answer", answer_node)
    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "answer")
    g.add_edge("answer", END)
    return g.compile()
