"""FastAPI routes for PromptLab"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from app.models import (
    Prompt, PromptCreate, PromptUpdate, PromptPatch,
    Collection, CollectionCreate,
    PromptList, CollectionList, HealthResponse,
    get_current_time
)
from app.storage import storage
from app.utils import sort_prompts_by_date, filter_prompts_by_collection, search_prompts
from app import __version__


app = FastAPI(
    title="PromptLab API",
    description="AI Prompt Engineering Platform",
    version=__version__
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== Health Check ==============

@app.get("/health", response_model=HealthResponse)
def health_check():
    """Return overall API health information.

    Returns:
        HealthResponse: Current health status and version metadata.

    Raises:
        None.
    """
    return HealthResponse(status="healthy", version=__version__)



# ============== Prompt Endpoints ==============

@app.get("/prompts", response_model=PromptList)
def list_prompts(
    collection_id: Optional[str] = None,
    search: Optional[str] = None
):
    """List prompts optionally filtered by collection and/or search query.

    Args:
        collection_id (Optional[str]): Collection identifier used to filter prompts.
        search (Optional[str]): Free-text query for prompt titles and descriptions.

    Returns:
        PromptList: Aggregated prompts and total count.

    Raises:
        None.
    """
    prompts = storage.get_all_prompts()
    
    # Filter by collection if specified
    if collection_id:
        prompts = filter_prompts_by_collection(prompts, collection_id)
    
    # Search if query provided
    if search:
        prompts = search_prompts(prompts, search)
    
    # Sort by date (newest first)
    # Note: There might be an issue with the sorting...
    prompts = sort_prompts_by_date(prompts, descending=True)
    
    return PromptList(prompts=prompts, total=len(prompts))

@app.get("/prompts/{prompt_id}", response_model=Prompt)
def get_prompt(prompt_id: str):
    """Fetch a single prompt by identifier.

    Args:
        prompt_id (str): Unique prompt identifier.

    Returns:
        Prompt: Prompt corresponding to the provided identifier.

    Raises:
        HTTPException: If the prompt does not exist.
    """
    prompt = storage.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt

# @app.get("/prompts/{prompt_id}", response_model=Prompt)
# def get_prompt(prompt_id: str):
#     # BUG #1: This will raise a 500 error if prompt doesn't exist
#     # because we're accessing .id on None
#     # Should return 404 instead!
#     prompt = storage.get_prompt(prompt_id)
    
#     # This line causes the bug - accessing attribute on None
#     if prompt.id:
#         return prompt


@app.post("/prompts", response_model=Prompt, status_code=201)
def create_prompt(prompt_data: PromptCreate):
    """Create a new prompt resource.

    Args:
        prompt_data (PromptCreate): Incoming prompt attributes.

    Returns:
        Prompt: Newly created prompt.

    Raises:
        HTTPException: If the referenced collection does not exist.
    """
    # Validate collection exists if provided
    if prompt_data.collection_id:
        collection = storage.get_collection(prompt_data.collection_id)
        if not collection:
            raise HTTPException(status_code=400, detail="Collection not found")
    
    prompt = Prompt(**prompt_data.model_dump())
    return storage.create_prompt(prompt)


@app.put("/prompts/{prompt_id}", response_model=Prompt)
def update_prompt(prompt_id: str, prompt_data: PromptUpdate):
    """Replace an existing prompt with updated data.

    Args:
        prompt_id (str): Identifier of the prompt to update.
        prompt_data (PromptUpdate): Complete set of prompt fields.

    Returns:
        Prompt: Updated prompt instance.

    Raises:
        HTTPException: If the prompt or referenced collection does not exist.
    """
    existing = storage.get_prompt(prompt_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    # Validate collection if provided
    if prompt_data.collection_id:
        collection = storage.get_collection(prompt_data.collection_id)
        if not collection:
            raise HTTPException(status_code=400, detail="Collection not found")
    
    # BUG #2: We're not updating the updated_at timestamp!
    # The updated prompt keeps the old timestamp
    updated_prompt = Prompt(
        id=existing.id,
        title=prompt_data.title,
        content=prompt_data.content,
        description=prompt_data.description,
        collection_id=prompt_data.collection_id,
        created_at=existing.created_at,
        updated_at=get_current_time()  
          # BUG: Should be get_current_time()
    )
    
    return storage.update_prompt(prompt_id, updated_prompt)


# PATCH endpoint allows partial updates (only provided fields are changed).

@app.patch("/prompts/{prompt_id}", response_model=Prompt)
def patch_prompt(prompt_id: str, prompt_data: PromptPatch):
    """Apply partial updates to a prompt.

    Args:
        prompt_id (str): Identifier of the prompt to modify.
        prompt_data (PromptPatch): Subset of fields to update.

    Returns:
        Prompt: Prompt after patching.

    Raises:
        HTTPException: If the prompt does not exist.
    """
    existing = storage.get_prompt(prompt_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # Apply only provided fields (PromptPatch uses Optional fields)

@app.delete("/prompts/{prompt_id}", status_code=204)
def delete_prompt(prompt_id: str):
    if not storage.delete_prompt(prompt_id):
        raise HTTPException(status_code=404, detail="Prompt not found")
    return None


# ============== Collection Endpoints ==============

@app.get("/collections", response_model=CollectionList)
def list_collections():
    collections = storage.get_all_collections()
    return CollectionList(collections=collections, total=len(collections))


@app.get("/collections/{collection_id}", response_model=Collection)
def get_collection(collection_id: str):
    collection = storage.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    return collection


@app.post("/collections", response_model=Collection, status_code=201)
def create_collection(collection_data: CollectionCreate):
    collection = Collection(**collection_data.model_dump())
    return storage.create_collection(collection)


@app.delete("/collections/{collection_id}", status_code=204)
def delete_collection(collection_id: str):
    # BUG #4: We delete the collection but don't handle the prompts!
    # Prompts with this collection_id become orphaned with invalid reference
    # Should either: delete the prompts, set collection_id to None, or prevent deletion
    
    if not storage.delete_collection(collection_id):
        raise HTTPException(status_code=404, detail="Collection not found")
    
    # Missing: Handle prompts that belong to this collection!
    
    return None
