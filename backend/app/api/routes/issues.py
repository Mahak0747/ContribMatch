from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_github_client
from app.schemas.issues import IssueSearchParams, IssueSearchResponse
from app.services.github_client import GitHubClient

router = APIRouter(prefix="/issues", tags=["issues"])


@router.get("/search", response_model=IssueSearchResponse)
async def search_issues(
    params: Annotated[IssueSearchParams, Query()],
    github: GitHubClient = Depends(get_github_client),
) -> IssueSearchResponse:
    """Search real, open GitHub issues (pull requests excluded).

    Example: `/api/issues/search?language=Python&labels=good first issue&labels=help wanted&domain=machine learning`
    """
    return await github.search_issues(params)
