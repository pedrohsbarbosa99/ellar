from ellar.auth import Authorize, CheckPolicies
from ellar.auth.policy import RequiredClaimsPolicy, RequiredRolePolicy
from ellar.common import Controller, get

from .policies import AdultOnly, AtLeast21


@Controller("/movies")
@Authorize()
class MoviesControllers:
    @get("/")
    @CheckPolicies(AdultOnly)
    async def fast_x(self):
        return "fast and furious 10"


@Controller("/article")
@Authorize()
class ArticleController:
    @get("/create")
    @CheckPolicies(RequiredClaimsPolicy("article", "create", "publish"))
    async def create_and_publish(self):
        return "fast and furious 10 Article"

    @get("/list")
    async def get_articles(self):
        return "List of articles"

    @get("/admin-only")
    @CheckPolicies(RequiredRolePolicy("admin"))
    async def admin_only(self):
        return "List of articles"

    @get("/staff-only")
    @CheckPolicies(RequiredRolePolicy("staff"))
    async def staff_only(self):
        return "List of articles"

    @get("/at-least-21")
    @CheckPolicies(AtLeast21["Tochi", "Udoh"])
    async def at_least_21(self):
        return "Only for Age of 21 or more"

    @get("/at-least-21-case-2")
    @CheckPolicies(AtLeast21["chinelo", "udoh"]() | AtLeast21["clara", "udoh"])
    async def at_least_21_case_2(self):
        return "Only for Age of 21 or more"
