import os
import re
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from backend.config import settings
from backend.utils.data_cleaner import load_and_preprocess_ledger

PERSIST_DIR = settings.CHROMA_DB_PATH
POLICY_DIR = settings.POLICY_DIR
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize Gemini Embeddings & Chat Models via LangChain
embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=GEMINI_API_KEY
)

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=GEMINI_API_KEY,
    temperature=0.2
)

POLICY_PROMPT = """
You are an AI Internal Auditor Assistant. Answer the compliance question strictly
based on the following corporate policy context. If context is insufficient, state
'Insufficient policy documentation found.'

Context:
{context}

Question:
{question}

Provide a concise answer with specific policy limits and thresholds:
"""

# Query is treated as "financial" (in-scope for this copilot) if it names a ledger
# transaction, or mentions any of these finance/audit terms; otherwise it's rejected
# before hitting the LLM so we don't burn a call (or hallucinate) on off-topic chatter.
FINANCIAL_KEYWORDS = re.compile(
    r"\b(ledger|txn|transaction|vendor|invoice|payment|payments|policy|polic\w*|audit|"
    r"threshold|duplicate|amount|budget|compliance|expense|procurement|approval|"
    r"reimbursement|lakh|fraud|risk|split|department|category|fiscal|tax|gst|"
    r"purchase\s*order|\bpo\b|contract|spend|cost)\b",
    re.IGNORECASE,
)

TXN_PATTERN = re.compile(r"\bTXN[\s\-#]*0*(\d+)\b", re.IGNORECASE)


def ingest_policy_documents():
    """Reads policy PDFs from data/policy_documents/, chunks them, generates embeddings,
    and persists them into ChromaDB."""
    documents = []

    if not os.path.exists(POLICY_DIR):
        os.makedirs(POLICY_DIR, exist_ok=True)

    for file in os.listdir(POLICY_DIR):
        if file.endswith(".pdf"):
            pdf_path = os.path.join(POLICY_DIR, file)
            loader = PyPDFLoader(pdf_path)
            documents.extend(loader.load())

    if not documents:
        print(f"No PDF documents found in {POLICY_DIR} to index.")
        return None

    # Text Chunking: 1000 characters per chunk, 200 overlap
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_documents(documents)

    # Persist to Chroma Vector Store
    vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=PERSIST_DIR,
        collection_name="audit_policies"
    )
    print(f"Successfully indexed {len(chunks)} chunks into ChromaDB at {PERSIST_DIR}.")
    return vector_store


def _fmt_amount(x: float) -> str:
    return f"{settings.CURRENCY_SYMBOL}{x:,.2f}"


def _compute_rule_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Deterministic THRESHOLD_BYPASS / DUPLICATE_PAYMENT flags for the given (already
    vendor-scoped) ledger frame — kept consistent with anomaly_engine's rule engine so
    RAG answers agree with what Module 2 flags."""
    df = df.copy()
    abs_amt = df['amount'].abs()
    band = settings.ANOMALY_THRESHOLD_BAND
    threshold_hit = pd.Series(False, index=df.index)
    for t in settings.ANOMALY_APPROVAL_THRESHOLDS:
        threshold_hit |= (abs_amt >= t * (1.0 - band)) & (abs_amt < t)

    df_sorted = df.sort_values(by=['vendor_name', 'amount', 'date'])
    same_vendor = df_sorted['vendor_name'] == df_sorted['vendor_name'].shift(-1)
    same_amount = (df_sorted['amount'] - df_sorted['amount'].shift(-1)).abs() < 0.01
    material = df_sorted['amount'].abs() >= settings.ANOMALY_DUP_MIN_AMOUNT
    dt_col = pd.to_datetime(df_sorted['date'])
    days_diff = (dt_col.shift(-1) - dt_col).dt.days.abs() <= settings.ANOMALY_DUP_WINDOW_DAYS
    dup_mask = same_vendor & same_amount & days_diff & material
    dup_set = set(df_sorted[dup_mask].index).union(set(df_sorted[dup_mask.shift(1).fillna(False)].index))

    df['is_threshold_bypass'] = threshold_hit
    df['is_duplicate_payment'] = df.index.isin(dup_set)
    return df


def _format_txn_row(row) -> str:
    flags = []
    if row.get('is_threshold_bypass'):
        flags.append('THRESHOLD_BYPASS')
    if row.get('is_duplicate_payment'):
        flags.append('DUPLICATE_PAYMENT')
    date_str = row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else str(row['date'])
    return (
        f"Txn {row['transaction_id']}: {_fmt_amount(row['amount'])} | Vendor: {row['vendor_name']} "
        f"({row.get('vendor_id', '-')}) | Dept: {row.get('department', '-')} | "
        f"Category: {row.get('category', '-')} | Date: {date_str} | "
        f"Flags: {', '.join(flags) if flags else 'None'}"
    )


def _lookup_ledger(user_query: str, vendor_id: str):
    """Handles ledger-grounded questions: direct Txn ID lookup, and aggregate rule
    queries (duplicate payments, threshold bypass, totals). Returns
    (answer_text_or_None, ledger_citations, matched)."""
    ql = user_query.lower()
    candidates = TXN_PATTERN.findall(user_query)

    try:
        df = load_and_preprocess_ledger(vendor_id=vendor_id)
    except Exception:
        return None, [], False

    if df.empty:
        return None, [], False

    df = _compute_rule_flags(df)
    ids_upper = df['transaction_id'].astype(str).str.upper()

    # 1. Direct transaction ID lookup (exact match first, then loose substring match).
    if candidates:
        lines, citations = [], []
        any_exact = False
        for num in candidates:
            exact = df[ids_upper == f"TXN-{num}"]
            if not exact.empty:
                any_exact = True
                for _, row in exact.iterrows():
                    lines.append(_format_txn_row(row))
                    citations.append({
                        "doc_name": f"Ledger — {row['transaction_id']}",
                        "page": 0,
                        "snippet": _format_txn_row(row),
                        "type": "ledger",
                    })
            else:
                fuzzy = df[ids_upper.str.contains(re.escape(num), regex=True)].head(5)
                if not fuzzy.empty:
                    lines.append(f"No exact match for TXN-{num} in the current vendor scope. Closest matches:")
                    for _, row in fuzzy.iterrows():
                        lines.append(_format_txn_row(row))
                        citations.append({
                            "doc_name": f"Ledger — {row['transaction_id']}",
                            "page": 0,
                            "snippet": _format_txn_row(row),
                            "type": "ledger",
                        })
                else:
                    lines.append(f"No transaction matching TXN-{num} was found in the current vendor scope.")
        if lines:
            return "\n".join(lines), citations, True

    # 2. Aggregate rule queries.
    if re.search(r"duplicate", ql):
        dup_df = df[df['is_duplicate_payment']]
        if dup_df.empty:
            return "No duplicate payments were found in the current vendor scope.", [], True
        lines = [f"{len(dup_df)} duplicate payment(s) found in scope:"]
        citations = []
        for _, row in dup_df.head(20).iterrows():
            lines.append(_format_txn_row(row))
            citations.append({
                "doc_name": f"Ledger — {row['transaction_id']}",
                "page": 0,
                "snippet": _format_txn_row(row),
                "type": "ledger",
            })
        return "\n".join(lines), citations, True

    if re.search(r"threshold[\s\-]*bypass", ql):
        tb_df = df[df['is_threshold_bypass']]
        if tb_df.empty:
            return "No threshold-bypass transactions were found in the current vendor scope.", [], True
        lines = [f"{len(tb_df)} threshold-bypass transaction(s) found in scope:"]
        citations = []
        for _, row in tb_df.head(20).iterrows():
            lines.append(_format_txn_row(row))
            citations.append({
                "doc_name": f"Ledger — {row['transaction_id']}",
                "page": 0,
                "snippet": _format_txn_row(row),
                "type": "ledger",
            })
        return "\n".join(lines), citations, True

    if re.search(r"total\s+(amount|spend)|grand\s+total|how many transaction|transaction count|count.*transaction", ql):
        total_amt = df['amount'].sum()
        return f"Current scope ({vendor_id}): {len(df)} transactions totaling {_fmt_amount(total_amt)}.", [], True

    return None, [], False


def query_policy_rag(user_query: str, top_k: int = 3, vendor_id: str = "ALL") -> dict:
    """Ledger-grounded + policy-grounded financial copilot.

    Resolves ledger Txn IDs and aggregate rule queries (duplicate payments,
    threshold bypass, totals) deterministically from the vendor-scoped ledger, and
    falls back to Gemini-backed retrieval over the policy PDF vector store for
    general compliance questions. Non-financial queries are rejected up front.
    """
    ledger_answer, ledger_citations, ledger_matched = _lookup_ledger(user_query, vendor_id)

    is_financial = bool(ledger_matched) or bool(FINANCIAL_KEYWORDS.search(user_query))

    retrieved_docs = []
    if not ledger_matched and is_financial:
        try:
            vector_store = Chroma(
                persist_directory=PERSIST_DIR,
                embedding_function=embeddings,
                collection_name="audit_policies"
            )
            retriever = vector_store.as_retriever(search_kwargs={"k": max(1, top_k)})
            retrieved_docs = retriever.invoke(user_query)
        except Exception:
            retrieved_docs = []

    policy_citations = [
        {
            "doc_name": os.path.basename(doc.metadata.get("source", "Unknown")),
            "page": doc.metadata.get("page", 0) + 1,
            "snippet": doc.page_content[:400].strip(),
            "type": "policy",
        }
        for doc in retrieved_docs
    ]

    if not is_financial:
        return {
            "answer": (
                "This assistant only answers financial ledger and corporate policy questions "
                "for your scoped vendor(s). Please rephrase as a ledger or policy question."
            ),
            "citations": [],
            "ledger_chunks": [],
            "retrieved_chunks": [],
            "is_financial": False,
            "vendor_scope": vendor_id,
        }

    if ledger_answer is not None:
        answer = ledger_answer
        citations = ledger_citations
    else:
        context_text = "\n\n".join(doc.page_content for doc in retrieved_docs)
        if not context_text.strip():
            answer = "Insufficient policy documentation found."
        else:
            prompt = ChatPromptTemplate.from_template(POLICY_PROMPT)
            chain = prompt | llm | StrOutputParser()
            answer = chain.invoke({"context": context_text, "question": user_query})
        citations = policy_citations

    return {
        "answer": answer,
        "citations": citations,
        "ledger_chunks": ledger_citations,
        "retrieved_chunks": policy_citations,
        "is_financial": True,
        "vendor_scope": vendor_id,
    }


# Backward compatibility alias
ingest_policy_pdfs = ingest_policy_documents


def get_chroma_collection():
    return Chroma(
        persist_directory=PERSIST_DIR,
        embedding_function=embeddings,
        collection_name="audit_policies"
    )


if __name__ == "__main__":
    print("Executing Policy RAG Ingestion Pipeline...")
    ingest_policy_documents()
    print("Testing query retrieval...")
    res = query_policy_rag("What are the travel per diem allowance rules?", vendor_id="ALL")
    print("Response:", res["answer"])
    print("Citations:", res["citations"])
