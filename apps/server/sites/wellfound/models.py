from typing import List, Optional, TypedDict
from pydantic import BaseModel, ValidationError
from dataclasses import dataclass


class RemoteConfig(BaseModel):
    id: str
    kind: str
    wfhFlexible: bool


class Badge(BaseModel):
    id: str
    label: str
    name: str
    tooltip: Optional[str] = None
    avatarUrl: Optional[str] = None
    data: Optional[str] = None
    rating: Optional[str] = None


class LocationTagging(BaseModel):
    displayName: str
    id: str


class JobListing(BaseModel):
    acceptedRemoteLocationNames: List[str]
    atsSource: Optional[str] = None
    autoPosted: bool
    currentUserApplied: bool
    description: str
    id: str
    jobType: str
    lastRespondedAt: Optional[int] = None
    liveStartAt: int
    locationNames: List[str]
    primaryRoleTitle: str
    remote: bool
    remoteConfig: Optional[RemoteConfig] = None
    reposted: bool
    slug: str
    title: str
    compensation: str
    equity: Optional[str] = None
    isBookmarked: bool
    companyName : Optional[str] = None
    companyId : Optional[str] = None

class StartupSearchResult(BaseModel):
    highlightedJobListings: List[JobListing]
    id: str
    startupId: str
    badges: List[Badge]
    companySize: str
    highConcept: Optional[str] = None      # can be null in API response
    locationTaggings: List[LocationTagging]
    logoUrl: str
    name: str
    slug: str
    newsStoryHeadline: Optional[str] = None
    newsStoryPublishedDate: Optional[str] = None
    newsStorySnippet: Optional[str] = None
    newsStorySource: Optional[str] = None
    newsStoryThumbnailUrl: Optional[str] = None
    newsStoryUrl: Optional[str] = None

class StartupSearchResultEdge(BaseModel):
    node: dict

    @staticmethod
    def _resolve_one(candidate: dict) -> Optional["StartupSearchResult"]:
        """
        Resolves a single node dict to StartupSearchResult, handling all known
        __typename wrappers recursively before attempting model validation.
        """
        typename = candidate.get("__typename", "")

        if typename == "PromotedResult":
            inner = candidate.get("promotedStartup")
            return StartupSearchResultEdge._resolve_one(inner) if inner else None

        if typename == "FeaturedStartup":
            inner = candidate.get("featuredStartup")
            return StartupSearchResultEdge._resolve_one(inner) if inner else None

        if typename == "StartupSearchResult":
            try:
                return StartupSearchResult.model_validate(candidate)
            except ValidationError as e:
                print(f"[SKIP] could not parse StartupSearchResult: {e}")
                return None

        print(f"[SKIP] unknown __typename '{typename}' during resolution")
        return None

    def resolve_startups(self) -> List["StartupSearchResult"]:
        typename = self.node.get("__typename", "")

        if typename == "FeaturedStartups":
            results = []
            for item in self.node.get("featuredStartups") or []:
                resolved = self._resolve_one(item)
                if resolved:
                    results.append(resolved)
            return results

        resolved = self._resolve_one(self.node)
        return [resolved] if resolved else []


class StartupSearchResultConnection(BaseModel):
    edges: List[StartupSearchResultEdge]


class JobSearchResults(BaseModel):
    hasNextPage: bool
    rawQuery: Optional[str] = None
    startups: StartupSearchResultConnection


class WellfoundTalent(BaseModel):
    jobSearchResults: JobSearchResults


class WellfoundData(BaseModel):
    talent: WellfoundTalent


class WellfoundResponse(BaseModel):
    data: WellfoundData


class JobListingRole(BaseModel):
    id: str


class JobListingStartup(BaseModel):
    id: str
    name: str
    logoUrl: str
    slug: str


class JobListingQualificationReport(BaseModel):
    errors: List[str]
    warnings: List[str]


class JobListingAiAssessment(BaseModel):
    id: str
    interviewUrl: str
    status: str


class JobListingCandidate(BaseModel):
    aiAssessment: Optional[JobListingAiAssessment] = None
    id: str


class JobListingViewer(BaseModel):
    currentCandidate: JobListingCandidate
    id: str


class JobListingTalent(BaseModel):
    viewer: JobListingViewer


class JobListingQuestion(BaseModel):
    id: str
    question: str       # maps to value
    kind: str           # "LONG", "SHORT" — both map to "text" format
    required: bool
    options: List[dict] # always empty for this type, ignored
    managedByAts: bool
    def to_application_question(self) -> "JobApplicationQuestion":
        return JobApplicationQuestion(
            id=self.id,
            value=self.question,
            format="text",
            required=self.required,
            options=None,
        )


class JobApplicationQuestionOption(BaseModel):
    label: str
    value: str

class JobApplicationQuestion(BaseModel):
    id: str
    value: Optional[str] = None            # present in applicationQuestionSets
    format: Optional[str] = None           # present in applicationQuestionSets
    required: bool
    options: Optional[List[JobApplicationQuestionOption]] = None
    placeholder: Optional[str] = None
    prefilledResponse: Optional[str] = None
    acceptedFileTypes: Optional[str] = None


class JobApplicationQuestionSet(BaseModel):
    id: str
    label: Optional[str] = None
    questions: List[JobApplicationQuestion]


class JobQuestionAnswer(TypedDict):
    jobListingQuestionId: str
    answer: str
    jobListingQuestionOptionId: Optional[str]


class JobListingDetail(BaseModel):
    id: str
    primaryRole: JobListingRole
    recruitingContact: Optional[dict] = None
    source: str
    aiAssessmentRequired: bool
    autoPosted: bool
    currentUserCompletedRequiredAiAssessment: Optional[bool] = None
    currentUserSharingAiAssessment: Optional[bool] = None
    offsiteListingUrl: Optional[str] = None
    startup: JobListingStartup
    acceptedRemoteLocationTags: List[LocationTagging]
    allowRelocation: bool
    currentUserQualificationReport: JobListingQualificationReport
    locationTags: List[dict]
    relocationAssistance: bool
    primaryRoleParent: str
    yearsExperienceMin: Optional[int] = None
    questions: List[JobListingQuestion]  
    applicationQuestionSets: List[JobApplicationQuestionSet]
    candidateNoteRequired: bool
    currentUserApplied: bool
    locationNames: List[str]
    public: bool
    remote: bool
    title: str
    compensation: Optional[str] = None
    equity: Optional[str] = None
    acceptedRemoteLocationNames: List[str]
    jobType: str
    liveStartAt: int
    remoteConfig: Optional[RemoteConfig] = None
    reposted: bool
    skills: List[dict]
    startupLocationNames: List[str]
    visaSponsorship: bool
    lastRespondedAt: Optional[int] = None


class JobApplicationModalData(BaseModel):
    jobListing: JobListingDetail
    talent: JobListingTalent


class JobApplicationModalResponse(BaseModel):
    data: JobApplicationModalData
    schemaVersion: int


class LLMError(Exception):
    pass

class SessionExpiredError(Exception):
    pass


@dataclass
class MatchResult:
    score: int          # 0-100
    reasoning: str
    strengths: list[str]
    gaps: list[str]
