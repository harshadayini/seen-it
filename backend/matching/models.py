"""Data contract models and schema validator for Seen It (`contracts/run.schema.json`).

What this module does:
    Defines typed Python 3.11 dataclasses mirroring every entity in
    `contracts/run.schema.json` (`Candidate`, `Preview`, `CartRef`, `Item`,
    `Source`, `Totals`, `Run`), provides bidirectional JSON serialization
    (`from_dict` / `to_dict`), and implements a zero-dependency validator that
    verifies payloads against the authoritative contract even when `jsonschema`
    is not installed.

Use cases:
    - Shared typed interfaces for P2's matching pipeline (`search`, `check`,
      `resolve`, `pick_within_budget`) and evaluation harness (`eval/`).
    - Validating `fixtures/sample_run.json` and live `run.json` outputs produced
      incrementally during `POST /run` and polled via `GET /run/<id>`.
    - Carrying optional transient desk-mode fit scores (`p_fits_style`,
      `p_fits_space`) in memory during budget optimization without polluting the
      serialized `contracts/run.schema.json` wire payload.

What this module must NOT do:
    - Must never alter the field names, required fields, or enum values defined
      in `contracts/run.schema.json` without approval from all three teammates.
    - Must never store merchant image bytes inside persisted run models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


RunState = Literal["processing", "done", "failed"]
RunMode = Literal["video", "desk"]
ItemStatus = Literal["exact", "similar", "none"]

VALID_STATES = frozenset({"processing", "done", "failed"})
VALID_MODES = frozenset({"video", "desk"})
VALID_STATUSES = frozenset({"exact", "similar", "none", None})


@dataclass
class Candidate:
    """A single Shopify product variant candidate scored for a detected item.

    Wire fields strictly mirror `$defs.candidate` in `contracts/run.schema.json`.
    `p_fits_style` and `p_fits_space` are ephemeral in-memory fields used only
    during desk-mode budget selection (`backend/matching/budget.py`) and are not
    emitted in the wire JSON contract.
    """

    title: str
    upid: str | None = None
    variant_id: str | None = None
    merchant_domain: str | None = None
    price: float | None = None
    currency: str | None = None
    image_url: str | None = None
    product_url: str | None = None  # merchant's product page (Shopify variant url), shown as "View on store"
    p_same_product: float | None = None
    p_same_variant: float | None = None
    # Ephemeral desk-mode scoring fields (kept out of to_dict() wire output)
    p_fits_style: float | None = field(default=None, repr=False)
    p_fits_space: float | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this candidate to a contract-compliant dictionary.

        Returns:
            Dictionary matching `$defs.candidate` in `contracts/run.schema.json`.

        Side effects:
            None.
        """
        return {
            "upid": self.upid,
            "variant_id": self.variant_id,
            "title": self.title,
            "merchant_domain": self.merchant_domain,
            "price": self.price,
            "currency": self.currency,
            "image_url": self.image_url,
            "product_url": self.product_url,
            "p_same_product": self.p_same_product,
            "p_same_variant": self.p_same_variant,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Candidate:
        """Construct a `Candidate` instance from a raw dictionary.

        Args:
            data: Dictionary containing at least `title` and optional candidate fields.

        Returns:
            Populated `Candidate` dataclass.

        Raises:
            ValueError: If `title` is missing or not a string.

        Side effects:
            None.
        """
        title = data.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Candidate requires a non-empty string 'title'.")
        return cls(
            title=title,
            upid=data.get("upid"),
            variant_id=data.get("variant_id"),
            merchant_domain=data.get("merchant_domain"),
            price=float(data["price"]) if data.get("price") is not None else None,
            currency=data.get("currency"),
            image_url=data.get("image_url"),
            product_url=data.get("product_url"),
            p_same_product=(
                float(data["p_same_product"])
                if data.get("p_same_product") is not None
                else None
            ),
            p_same_variant=(
                float(data["p_same_variant"])
                if data.get("p_same_variant") is not None
                else None
            ),
        )


@dataclass
class Preview:
    """Optional 'See it here' generated preview metadata for an item."""

    image_path: str | None = None
    fidelity: float | None = None
    regenerated: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize preview metadata to a contract-compliant dictionary.

        Returns:
            Dictionary matching `item.preview` in `contracts/run.schema.json`.

        Side effects:
            None.
        """
        return {
            "image_path": self.image_path,
            "fidelity": self.fidelity,
            "regenerated": self.regenerated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Preview | None:
        """Construct a `Preview` instance from a dictionary or `None`.

        Args:
            data: Raw dictionary or `None`.

        Returns:
            `Preview` instance or `None`.

        Side effects:
            None.
        """
        if data is None:
            return None
        return cls(
            image_path=data.get("image_path"),
            fidelity=(
                float(data["fidelity"]) if data.get("fidelity") is not None else None
            ),
            regenerated=data.get("regenerated"),
        )


@dataclass
class CartRef:
    """Shopify per-merchant cart reference and checkout handoff URL."""

    cart_id: str | None = None
    continue_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize cart reference metadata to a contract-compliant dictionary.

        Returns:
            Dictionary matching `item.cart` in `contracts/run.schema.json`.

        Side effects:
            None.
        """
        return {
            "cart_id": self.cart_id,
            "continue_url": self.continue_url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CartRef | None:
        """Construct a `CartRef` instance from a dictionary or `None`.

        Args:
            data: Raw dictionary or `None`.

        Returns:
            `CartRef` instance or `None`.

        Side effects:
            None.
        """
        if data is None:
            return None
        return cls(
            cart_id=data.get("cart_id"),
            continue_url=data.get("continue_url"),
        )


@dataclass
class Item:
    """A single purchasable product detected in a video or requested in desk mode."""

    item_id: str
    state: RunState = "processing"
    t_start: float | None = None
    t_end: float | None = None
    crop_path: str | None = None
    description: str | None = None
    attributes: dict[str, Any] | None = None
    query: str | None = None
    candidates: list[Candidate] = field(default_factory=list)
    status: ItemStatus | None = None
    recovered: bool | None = False
    preview: Preview | None = None
    cart: CartRef | None = None
    # Ephemeral structured error note for backend diagnostics (never hides failed state)
    error: str | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this item to a contract-compliant dictionary.

        Returns:
            Dictionary matching `$defs.item` in `contracts/run.schema.json`.

        Side effects:
            None.
        """
        return {
            "item_id": self.item_id,
            "state": self.state,
            "t_start": self.t_start,
            "t_end": self.t_end,
            "crop_path": self.crop_path,
            "description": self.description,
            "attributes": self.attributes,
            "query": self.query,
            "candidates": [c.to_dict() for c in self.candidates],
            "status": self.status,
            "recovered": self.recovered,
            "preview": self.preview.to_dict() if self.preview is not None else None,
            "cart": self.cart.to_dict() if self.cart is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Item:
        """Construct an `Item` instance from a raw dictionary.

        Args:
            data: Raw item dictionary conforming to `$defs.item`.

        Returns:
            Populated `Item` dataclass.

        Raises:
            ValueError: If required fields (`item_id`, `state`) are missing or invalid.

        Side effects:
            None.
        """
        item_id = data.get("item_id")
        state = data.get("state")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("Item requires a non-empty string 'item_id'.")
        if state not in VALID_STATES:
            raise ValueError(f"Invalid item state '{state}'. Expected one of {sorted(VALID_STATES)}.")
        status = data.get("status")
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid item status '{status}'.")
        return cls(
            item_id=item_id,
            state=state,
            t_start=float(data["t_start"]) if data.get("t_start") is not None else None,
            t_end=float(data["t_end"]) if data.get("t_end") is not None else None,
            crop_path=data.get("crop_path"),
            description=data.get("description"),
            attributes=dict(data["attributes"]) if data.get("attributes") is not None else None,
            query=data.get("query"),
            candidates=[Candidate.from_dict(c) for c in data.get("candidates", [])],
            status=status,
            recovered=data.get("recovered"),
            preview=Preview.from_dict(data.get("preview")),
            cart=CartRef.from_dict(data.get("cart")),
        )


@dataclass
class Source:
    """Input media metadata for a Seen It run."""

    video_id: str | None = None
    duration_s: float | None = None
    budget_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize source metadata to a contract-compliant dictionary.

        Returns:
            Dictionary matching `source` in `contracts/run.schema.json`.

        Side effects:
            None.
        """
        return {
            "video_id": self.video_id,
            "duration_s": self.duration_s,
            "budget_usd": self.budget_usd,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Source:
        """Construct a `Source` instance from a raw dictionary.

        Args:
            data: Raw source dictionary.

        Returns:
            Populated `Source` dataclass.

        Side effects:
            None.
        """
        return cls(
            video_id=data.get("video_id"),
            duration_s=(
                float(data["duration_s"]) if data.get("duration_s") is not None else None
            ),
            budget_usd=(
                float(data["budget_usd"]) if data.get("budget_usd") is not None else None
            ),
        )


@dataclass
class Totals:
    """Aggregated price and budget compliance summary for a run."""

    price: float | None = None
    within_budget: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize totals to a contract-compliant dictionary.

        Returns:
            Dictionary matching `totals` in `contracts/run.schema.json`.

        Side effects:
            None.
        """
        return {
            "price": self.price,
            "within_budget": self.within_budget,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Totals:
        """Construct a `Totals` instance from a raw dictionary.

        Args:
            data: Raw totals dictionary.

        Returns:
            Populated `Totals` dataclass.

        Side effects:
            None.
        """
        return cls(
            price=float(data["price"]) if data.get("price") is not None else None,
            within_budget=data.get("within_budget"),
        )


@dataclass
class Run:
    """Top-level Seen It run payload persisted to `run.json` and polled by the UI."""

    run_id: str
    state: RunState
    mode: RunMode
    source: Source
    items: list[Item] = field(default_factory=list)
    totals: Totals = field(default_factory=Totals)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this run to a contract-compliant dictionary.

        Returns:
            Dictionary matching the root schema in `contracts/run.schema.json`.

        Side effects:
            None.
        """
        return {
            "run_id": self.run_id,
            "state": self.state,
            "mode": self.mode,
            "source": self.source.to_dict(),
            "items": [item.to_dict() for item in self.items],
            "totals": self.totals.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Run:
        """Construct a `Run` instance from a raw dictionary.

        Args:
            data: Raw run dictionary conforming to `contracts/run.schema.json`.

        Returns:
            Populated `Run` dataclass.

        Raises:
            ValueError: If required top-level fields or enums are invalid.

        Side effects:
            None.
        """
        errors = validate_run_dict(data)
        if errors:
            raise ValueError(f"Run payload failed contract validation: {'; '.join(errors)}")
        return cls(
            run_id=data["run_id"],
            state=data["state"],
            mode=data["mode"],
            source=Source.from_dict(data["source"]),
            items=[Item.from_dict(i) for i in data["items"]],
            totals=Totals.from_dict(data["totals"]),
        )


def _is_number(value: Any) -> bool:
    """Return True if `value` is an int or float (excluding bool).

    Args:
        value: Arbitrary object to test.

    Returns:
        Boolean indicating JSON numeric compatibility.

    Side effects:
        None.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_run_dict(data: Any) -> list[str]:
    """Validate a raw dictionary against `contracts/run.schema.json` without third-party deps.

    Args:
        data: Deserialized JSON payload expected to match `run.schema.json`.

    Returns:
        A list of human-readable validation error strings (empty list means valid).

    Side effects:
        None.
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Root payload must be a JSON object."]

    required_root = ("run_id", "state", "mode", "source", "items", "totals")
    for req in required_root:
        if req not in data:
            errors.append(f"Missing required root field '{req}'.")

    if "run_id" in data and not isinstance(data["run_id"], str):
        errors.append("Field 'run_id' must be a string.")
    if "state" in data and data["state"] not in VALID_STATES:
        errors.append(f"Field 'state' must be one of {sorted(VALID_STATES)}.")
    if "mode" in data and data["mode"] not in VALID_MODES:
        errors.append(f"Field 'mode' must be one of {sorted(VALID_MODES)}.")

    source = data.get("source")
    if source is not None:
        if not isinstance(source, dict):
            errors.append("Field 'source' must be an object.")
        else:
            if source.get("video_id") is not None and not isinstance(source["video_id"], str):
                errors.append("source.video_id must be a string or null.")
            if source.get("duration_s") is not None and not _is_number(source["duration_s"]):
                errors.append("source.duration_s must be a number or null.")
            if source.get("budget_usd") is not None and not _is_number(source["budget_usd"]):
                errors.append("source.budget_usd must be a number or null.")

    totals = data.get("totals")
    if totals is not None:
        if not isinstance(totals, dict):
            errors.append("Field 'totals' must be an object.")
        else:
            if totals.get("price") is not None and not _is_number(totals["price"]):
                errors.append("totals.price must be a number or null.")
            if totals.get("within_budget") is not None and not isinstance(
                totals["within_budget"], bool
            ):
                errors.append("totals.within_budget must be a boolean or null.")

    items = data.get("items")
    if items is not None:
        if not isinstance(items, list):
            errors.append("Field 'items' must be an array.")
        else:
            for idx, item in enumerate(items):
                prefix = f"items[{idx}]"
                if not isinstance(item, dict):
                    errors.append(f"{prefix} must be an object.")
                    continue
                if not isinstance(item.get("item_id"), str):
                    errors.append(f"{prefix}.item_id must be a string.")
                if item.get("state") not in VALID_STATES:
                    errors.append(f"{prefix}.state must be one of {sorted(VALID_STATES)}.")
                if "status" in item and item["status"] not in VALID_STATUSES:
                    errors.append(f"{prefix}.status must be 'exact', 'similar', 'none', or null.")
                if item.get("recovered") is not None and not isinstance(item["recovered"], bool):
                    errors.append(f"{prefix}.recovered must be a boolean or null.")
                for num_field in ("t_start", "t_end"):
                    if item.get(num_field) is not None and not _is_number(item[num_field]):
                        errors.append(f"{prefix}.{num_field} must be a number or null.")

                candidates = item.get("candidates", [])
                if not isinstance(candidates, list):
                    errors.append(f"{prefix}.candidates must be an array.")
                else:
                    for c_idx, cand in enumerate(candidates):
                        c_prefix = f"{prefix}.candidates[{c_idx}]"
                        if not isinstance(cand, dict):
                            errors.append(f"{c_prefix} must be an object.")
                            continue
                        if not isinstance(cand.get("title"), str):
                            errors.append(f"{c_prefix}.title must be a string.")
                        if cand.get("price") is not None and not _is_number(cand["price"]):
                            errors.append(f"{c_prefix}.price must be a number or null.")
                        for prob_field in ("p_same_product", "p_same_variant"):
                            prob = cand.get(prob_field)
                            if prob is not None:
                                if not _is_number(prob) or not (0.0 <= prob <= 1.0):
                                    errors.append(
                                        f"{c_prefix}.{prob_field} must be a number in [0, 1] or null."
                                    )
    return errors
