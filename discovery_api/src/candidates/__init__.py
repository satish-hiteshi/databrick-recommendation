"""candidates — the candidate-pool providers (P3). Each turns (UserProfile, RequestContext) into a list
of Candidate stubs with RAW signals; the P4 scorer blends them and P5 assembles feed + carousels.

Providers:
  SimilarToFollowed   personalized vector neighbours of followed/reacted entities (podcast = vector-only)
  FreshMoments        main-feed source: fresh moments from unfollowed properties (per-property cap)
  TrendingGlobal      global cold-start backbone: influence + velocity + recency, cached per cadence
  PopularWithFansOf   personalized: graph_similar (game/movie/tv) | vector (podcast) + co-follow
  NewInGenre          fresh moments grouped by genre (canonical_genres | podcast categories)
  NewOnPlatform       fresh moments grouped by media_platform (moment + CTA platforms)
"""

from .base import Candidate, CandidateProvider, RequestContext, dedupe, excluded_entity_ids, select_fresh_moments
from .fresh_moments import FreshMoments
from .new_in_genre import NewInGenre
from .new_on_platform import NewOnPlatform
from .popular_with_fans_of import PopularWithFansOf
from .similar_to_followed import SimilarToFollowed
from .trending_global import TrendingGlobal

__all__ = ["Candidate", "CandidateProvider", "RequestContext", "dedupe", "excluded_entity_ids",
           "select_fresh_moments", "SimilarToFollowed", "FreshMoments", "TrendingGlobal",
           "PopularWithFansOf", "NewInGenre", "NewOnPlatform", "ALL_PROVIDERS"]

# personalized pools are empty for cold-start; global/fresh pools carry it
ALL_PROVIDERS = [SimilarToFollowed, FreshMoments, TrendingGlobal, PopularWithFansOf, NewInGenre, NewOnPlatform]
