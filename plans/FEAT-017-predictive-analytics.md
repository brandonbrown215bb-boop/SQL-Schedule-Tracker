# FEAT-017: Predictive Analytics for Scheduling

**Status**: Draft  
**Priority**: Medium  
**Effort**: XL (16 days)  
**Depends on**: ARCH-001, PERF-002  

---

## Problem Statement

Capacity checks currently rely on hardcoded constants and simple threshold comparisons. This results in:

- **No risk forecasting** — cannot predict which units are likely to miss their due dates
- **No workload trends** — cannot see if a detailer's workload is increasing or decreasing over time
- **No bottleneck prediction** — cannot identify where the checking pipeline will choke before it happens
- **No what-if analysis** — cannot simulate the impact of reassignments or schedule changes
- **No data-driven insights** — dashboards show current state only, not projected future state

---

## Proposed Solution

Implement a pure-Python predictive analytics engine that provides:

1. **Due-date risk scoring** — Monte Carlo simulation estimating probability of on-time completion
2. **Detailer workload forecasting** — moving average projections with confidence intervals
3. **Bottleneck prediction** — queueing theory applied to the checking pipeline
4. **What-if scenario modeling** — simulate reassignments, deadline changes, and resource shifts
5. **Trend dashboards** — visualizations of key metrics over time

No external machine learning libraries are used. All algorithms are implemented with `numpy` and `statistics` from the standard library.

---

## 1. Due-Date Risk Scoring (Monte Carlo)

### Method

For each unit, we simulate N=10,000 possible completion dates based on historical processing times, then compute the probability that completion occurs before the due date.

```
Given:
  - Historical completion times: T = {t1, t2, ..., tn} (in days)
  - Current progress: p (0.0 to 1.0)
  - Due date: D
  - Current date: C

For each simulation iteration i = 1 to N:
  1. Sample a random completion time t_i from the empirical distribution of T
  2. Adjust for remaining work: remaining_days = t_i * (1 - p)
  3. Compute projected completion: C + remaining_days
  4. Mark as "on-time" if projected <= D

Risk score = 1 - (on_time_count / N)
```

### Algorithm Pseudocode

```
FUNCTION compute_risk_score(unit, historical_data, n_simulations=10000)
    history = historical_data.get_completion_times(
        detailer=unit.detailer,
        unit_type=unit.unit_type,
        lookback_days=365
    )
    IF length(history) < MIN_SAMPLES:
        RETURN "insufficient-data"

    current_progress = unit.percent_complete  // 0.0 to 1.0
    remaining_work = 1.0 - current_progress
    on_time_count = 0

    FOR i = 1 TO n_simulations:
        // Bootstrap resample from history
        sample_idx = random_integer(0, length(history) - 1)
        sample_days = history[sample_idx]

        // Scale by remaining work
        projected_days = sample_days * remaining_work

        // Account for daily variation
        daily_noise = normal(mean=0.0, stddev=0.3)
        projected_days = max(0.1, projected_days + daily_noise)

        projected_date = today() + timedelta(days=projected_days)

        IF projected_date <= unit.detailing_due_date:
            on_time_count += 1

    risk_score = 1.0 - (on_time_count / n_simulations)
    RETURN risk_score
END FUNCTION
```

### Risk Score Interpretation

| Score Range | Label | Color | Action |
|-------------|-------|-------|--------|
| 0.00 – 0.20 | Low Risk | Green | No action needed |
| 0.21 – 0.40 | Moderate Risk | Yellow | Monitor weekly |
| 0.41 – 0.60 | Elevated Risk | Orange | Review within 3 days |
| 0.61 – 0.80 | High Risk | Red | Escalate to supervisor |
| 0.81 – 1.00 | Critical | Dark Red | Immediate intervention |

---

## 2. Detailer Workload Forecasting (Moving Averages)

### Method

We use a weighted moving average with exponential smoothing to project a detailer's future workload based on incoming units and their expected completion rates.

```
Given:
  - Detailer's current assigned units: U = {u1, u2, ..., uk}
  - Each unit has: remaining_days, priority, estimated_hours
  - Historical throughput: H = daily completions over last 90 days

Compute:
  1. Base throughput rate: λ = mean(H)  (units per day)
  2. Trend component: m = linear_regression_slope(H)  (units/day/day)
  3. Seasonal factor: s_day_of_week = average_completions(day) / λ

Forecast for day t:
  forecast(t) = (λ + m * t) * s_day_of_week[t mod 7]
```

### Algorithm Pseudocode

```
FUNCTION forecast_workload(detailer, lookahead_days=30)
    history = get_daily_completions(detailer, lookback_days=90)
    active_units = get_active_units(detailer)

    // Base rate
    lambda_rate = mean(history)
    if lambda_rate < 0.01:
        return "insufficient-data"

    // Trend
    x = [1, 2, ..., length(history)]
    y = history
    slope, intercept = linear_regression(x, y)

    // Day-of-week factors
    day_factors = [0] * 7
    day_counts = [0] * 7
    for i, count in enumerate(history):
        day_of_week = i % 7
        day_factors[day_of_week] += count
        day_counts[day_of_week] += 1
    for d in range(7):
        if day_counts[d] > 0:
            day_factors[d] = day_factors[d] / day_counts[d] / lambda_rate
        else:
            day_factors[d] = 1.0

    // Generate forecast
    forecast = []
    for t in range(1, lookahead_days + 1):
        trend_component = lambda_rate + slope * t
        seasonal_component = day_factors[(t - 1) % 7]
        forecast_value = max(0, trend_component * seasonal_component)
        forecast.append(forecast_value)

    // Confidence interval
    residuals = [history[i] - (lambda_rate + slope * (i + 1)) for i in range(len(history))]
    std_error = stddev(residuals)
    ci_upper = [f + 1.96 * std_error for f in forecast]
    ci_lower = [max(0, f - 1.96 * std_error) for f in forecast]

    RETURN {
        "forecast": forecast,
        "ci_upper": ci_upper,
        "ci_lower": ci_lower,
        "current_backlog": len(active_units),
        "lambda": lambda_rate,
        "trend": slope
    }
END FUNCTION
```

### Visualization

```
Detailer Workload Forecast: Brandon B
─────────────────────────────────────

Units   │
per day │
        │                   ┌────┐
    3.0 │                   │    │  ▲ CI Upper
        │              ┌────┐    │  ─ Forecast
    2.5 │              │    │    │  ▼ CI Lower
        │         ┌────┐    │    │
    2.0 │         │    │    │    │
        │    ┌────┐    │    │    │
    1.5 │    │    │    │    │    │
        │ ┌──┘    │    │    │    │
    1.0 │─┘       │    │    │    │
        │         │    │    │    │
    0.5 │         │    │    │    │
        │         │    │    │    │
    0.0 └─────────────────────────►
        │ Past 30d │ │ Forecast 30d│
        └──────────────────────────
```

---

## 3. Bottleneck Prediction (Queueing Theory)

### Method

Model the checking pipeline as an M/M/1 queue where:
- Arrival rate (λ): incoming units per day to the checking queue
- Service rate (μ): units checked per day by available checkers

```
Key metrics:
  Utilization: ρ = λ / μ
  Queue length: Lq = ρ² / (1 - ρ)    [if ρ < 1]
  Wait time:   Wq = Lq / λ           [if ρ < 1]
  Probability of n units in system: P(n) = (1 - ρ) * ρⁿ

When ρ >= 1, the queue is unstable and will grow indefinitely.
```

### Algorithm Pseudocode

```
FUNCTION predict_bottleneck(lookahead_days=30)
    // Current state
    incoming_rate = mean(arrivals_last_30_days())
    checking_capacity = sum(checker_availability_last_30_days())
    service_rate = checking_capacity / 30

    queue_backlog = get_current_checking_queue_length()
    predicted_queue = []

    FOR day in 1 TO lookahead_days:
        // Predict arrivals using workload forecast
        predicted_arrivals = forecast_arrivals(day)

        // Predict capacity using schedule
        predicted_capacity = forecast_checker_capacity(day)

        // Update queue
        queue_backlog = queue_backlog + predicted_arrivals - predicted_capacity
        queue_backlog = max(0, queue_backlog)

        ρ = predicted_arrivals / max(predicted_capacity, 0.01)
        predicted_queue.append({
            "day": day,
            "arrivals": predicted_arrivals,
            "capacity": predicted_capacity,
            "queue_length": queue_backlog,
            "utilization": min(ρ, 2.0),
            "bottleneck": queue_backlog > THRESHOLD_QUEUE_LENGTH
        })

    RETURN predicted_queue
END FUNCTION
```

### Bottleneck Heatmap

```
Checking Pipeline: 30-Day Projection
────────────────────────────────────

Day │ Arrivals  Capacity  Queue   Util   Status
────┼────────────────────────────────────────────
  1 │    12        14        2     86%    ✅ OK
  2 │    14        14        2    100%    ⚠️ At capacity
  3 │    10        14        0     71%    ✅ OK
  4 │    11        10        1    110%    🔴 Bottleneck!
  5 │    13        10        4    130%    🔴 Bottleneck!
  6 │    15        12        7    125%    🔴 Bottleneck!
  7 │     9        14        2     64%    ✅ OK
  8 │    10        14        0     71%    ✅ OK
  9 │    14        14        0    100%    ⚠️ At capacity
 10 │    12        14        0     86%    ✅ OK
```

---

## 4. What-If Scenario Modeling

### Method

Allow users to define hypothetical changes and simulate their impact across all metrics.

#### Scenario Types

| Scenario | Input | Output Metrics |
|----------|-------|----------------|
| Reassign units | Unit IDs + target detailer | Risk scores, workload balance, completion dates |
| Shift due dates | Unit IDs + new due date | Risk scores, critical path, queue lengths |
| Add/remove detailer | Detailer name + effective date | Workload distribution, capacity |
| Change priority | Unit IDs + new priority | Re-ranked risk list |
| Add overtime | Detailer + hours/week | Service rate, queue reduction |

### Algorithm Pseudocode

```
FUNCTION run_what_if(scenario_type, params, baseline_state)
    state = deep_copy(baseline_state)
    results = []

    CASE scenario_type:
        "reassign":
            units = params["unit_ids"]
            target = params["target_detailer"]
            FOR each unit IN units:
                source = unit.detailer
                state.remove_unit_from_detailer(unit, source)
                state.add_unit_to_detailer(unit, target)
            results = {
                "source": {
                    "detailer": source,
                    "new_workload": forecast_workload(source),
                    "risk_changes": compute_risk_delta(source)
                },
                "target": {
                    "detailer": target,
                    "new_workload": forecast_workload(target),
                    "risk_changes": compute_risk_delta(target)
                },
                "net_effect": {
                    "avg_risk_change": compute_average_risk_delta(state),
                    "bottleneck_impact": check_bottleneck_change(state)
                }
            }

        "shift_dates":
            FOR each unit IN params["unit_ids"]:
                unit.detailing_due_date = params["new_due_date"]
            results = {
                "unit_impacts": [compute_risk_score(u) for u in units],
                "pipeline": predict_bottleneck(),
                "critical_path": compute_critical_path(state)
            }

        "add_resource":
            detailer_name = params["detailer_name"]
            capacity_add = params["additional_capacity"]
            state.add_checker_capacity(capacity_add, params["effective_date"])
            results = {
                "new_service_rate": state.checking_service_rate,
                "new_utilization": state.arrival_rate / state.checking_service_rate,
                "queue_reduction": state.current_backlog - predict_backlog(state),
                "time_to_clear_queue": state.current_backlog / state.checking_service_rate
            }

    RETURN results
END FUNCTION
```

---

## 5. Trend Dashboards

### Key Metrics

| Metric | Aggregation | Frequency | Display |
|--------|-------------|-----------|---------|
| Avg risk score | Mean across all active units | Daily | Line chart (30-day) |
| Detailer workload | Units assigned per detailer | Weekly | Bar chart |
| Queue length | Checking pipeline size | Daily | Area chart |
| On-time rate | % completed before due date | Weekly | Gauge + trend |
| Capacity utilization | ρ per checking team | Daily | Heatmap |
| Risk distribution | Count per risk bucket | Weekly | Stacked bar |

### Dashboard Layout (ASCII)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 🔮 Predictive Analytics Dashboard                    [1mo ▾][3mo ▾][6mo ▾] │
├─────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────┐  ┌─────────────────────────┐               │
│ │  Avg Risk Score (30d)   │  │  On-Time Rate (Weekly)  │               │
│ │                         │  │                         │               │
│ │  0.8 ┤   ╱╲              │  │ 100% ┤ ┌──┐             │               │
│ │  0.6 ┤ ╱  ╲   ┌──┐      │  │  80% ┤ │  │ ┌──┐       │               │
│ │  0.4 ┤╱    ╲──┘  │      │  │  60% ┤ │  │ │  │       │               │
│ │  0.2 ┤      ╲    │      │  │  40% ┤ │  │ │  │       │               │
│ │      └──────────────    │  │      └────────────      │               │
│ │      ██████████████     │  │      ████████████       │               │
│ └─────────────────────────┘  └─────────────────────────┘               │
│                                                                         │
│ ┌─────────────────────────┐  ┌─────────────────────────┐               │
│ │  Checking Queue (30d)   │  │  Risk Distribution      │               │
│ │                         │  │                         │               │
│ │  20 ┤      ┌──┐         │  │  100% ┤ ██  ██  ██  ██  │               │
│ │  15 ┤  ┌──┐│  │ ┌──┐   │  │  80% ┤ ██  ██  ██  ██  │               │
│ │  10 ┤  │  ││  │ │  │   │  │  60% ┤ ██  ██  ██  ██  │               │
│ │   5 ┤  │  ││  │ │  │   │  │  40% ┤ ██  ██  ██  ██  │  ██ Critical  │
│ │   0 ┤──┘  └┘──┘ └──┘  │  │  20% ┤ ██  ██  ██  ██  │  ██ High      │
│ │      └──────────────    │  │   0% ┤──  ──  ──  ──  │  ██ Moderate  │
│ │      ██████████████     │  │      W1   W2   W3   W4 │  ██ Low       │
│ └─────────────────────────┘  └─────────────────────────┘               │
└─────────────────────────────────────────────────────────────────────────┘
```

### Core Analytics Engine

```python
# analytics/engine.py

import random
import math
from statistics import mean, stdev, median
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Any


@dataclass
class RiskAssessment:
    unit_id: str
    risk_score: float
    risk_label: str
    n_simulations: int
    projected_completion_date: datetime | None
    confidence_interval: tuple[float, float]


@dataclass
class WorkloadForecast:
    detailer: str
    forecast: list[float]
    ci_upper: list[float]
    ci_lower: list[float]
    current_backlog: int
    trend: float


@dataclass
class BottleneckPrediction:
    day: int
    arrivals: float
    capacity: float
    queue_length: float
    utilization: float
    is_bottleneck: bool


class AnalyticsEngine:
    """Pure-Python predictive analytics engine."""
    
    MIN_SAMPLES = 10
    N_SIMULATIONS = 10000
    LOOKAHEAD_DAYS = 30
    THRESHOLD_QUEUE_LENGTH = 5
    
    def __init__(self, data_provider: Any):
        self._data = data_provider
    
    def compute_risk_score(self, unit: Any) -> RiskAssessment:
        """Monte Carlo risk assessment for a single unit."""
        history = self._data.get_completion_times(
            detailer=unit.detailer,
            unit_type=unit.unit_type,
            lookback_days=365
        )
        
        if len(history) < self.MIN_SAMPLES:
            return RiskAssessment(
                unit_id=unit.com_number,
                risk_score=-1.0,
                risk_label="insufficient-data",
                n_simulations=0,
                projected_completion_date=None,
                confidence_interval=(0.0, 0.0)
            )
        
        current_progress = getattr(unit, 'percent_complete', 0.0)
        remaining_work = max(0.1, 1.0 - current_progress)
        due_date = unit.detailing_due_date
        
        on_time_count = 0
        completion_dates = []
        
        for _ in range(self.N_SIMULATIONS):
            sample = random.choice(history)
            projected_days = sample * remaining_work
            daily_noise = random.gauss(0.0, 0.3)
            projected_days = max(0.1, projected_days + daily_noise)
            projected = datetime.now() + timedelta(days=projected_days)
            completion_dates.append(projected)
            if due_date and projected <= due_date:
                on_time_count += 1
        
        risk_score = 1.0 - (on_time_count / self.N_SIMULATIONS)
        
        # Compute confidence interval from completion dates
        sorted_dates = sorted(completion_dates)
        ci_lower = (sorted_dates[int(self.N_SIMULATIONS * 0.05)] - datetime.now()).days
        ci_upper = (sorted_dates[int(self.N_SIMULATIONS * 0.95)] - datetime.now()).days
        
        risk_label = self._score_to_label(risk_score)
        
        return RiskAssessment(
            unit_id=unit.com_number,
            risk_score=risk_score,
            risk_label=risk_label,
            n_simulations=self.N_SIMULATIONS,
            projected_completion_date=median(completion_dates),
            confidence_interval=(ci_lower, ci_upper)
        )
    
    def forecast_detailer_workload(self, detailer: str) -> WorkloadForecast:
        """Moving-average workload forecast for a detailer."""
        history = self._data.get_daily_completions(detailer, lookback_days=90)
        active_units = self._data.get_active_units(detailer)
        
        if len(history) < 7:
            return WorkloadForecast(
                detailer=detailer,
                forecast=[],
                ci_upper=[],
                ci_lower=[],
                current_backlog=len(active_units),
                trend=0.0
            )
        
        lambda_rate = mean(history)
        if lambda_rate < 0.01:
            lambda_rate = 0.01
        
        # Linear trend
        n = len(history)
        x = list(range(1, n + 1))
        x_mean = mean(x)
        y_mean = mean(history)
        slope = (sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, history)) /
                 sum((xi - x_mean) ** 2 for xi in x))
        intercept = y_mean - slope * x_mean
        
        # Day-of-week adjustment
        day_factors = [1.0] * 7
        day_sums = [0.0] * 7
        day_counts = [0] * 7
        for i, count in enumerate(history):
            d = i % 7
            day_sums[d] += count
            day_counts[d] += 1
        for d in range(7):
            if day_counts[d] > 0:
                day_factors[d] = day_sums[d] / day_counts[d] / lambda_rate
        
        # Generate forecast
        forecast = []
        for t in range(1, self.LOOKAHEAD_DAYS + 1):
            trend_comp = lambda_rate + slope * t
            seasonal_comp = day_factors[(t - 1) % 7]
            fv = max(0.0, trend_comp * seasonal_comp)
            forecast.append(fv)
        
        # Confidence intervals from residuals
        residuals = [history[i] - (intercept + slope * (i + 1)) for i in range(n)]
        std_error = stdev(residuals) if len(residuals) > 1 else 0.5
        
        ci_upper = [f + 1.96 * std_error for f in forecast]
        ci_lower = [max(0.0, f - 1.96 * std_error) for f in forecast]
        
        return WorkloadForecast(
            detailer=detailer,
            forecast=forecast,
            ci_upper=ci_upper,
            ci_lower=ci_lower,
            current_backlog=len(active_units),
            trend=slope
        )
    
    def predict_bottlenecks(self) -> list[BottleneckPrediction]:
        """Queueing-theory bottleneck predictions for checking pipeline."""
        arrivals = self._data.get_arrivals_last_n_days(30)
        capacity = self._data.get_checking_capacity_last_n_days(30)
        
        arrival_rate = mean(arrivals) if arrivals else 0.0
        service_rate = mean(capacity) if capacity else 1.0
        queue_backlog = self._data.get_current_checking_queue_length()
        
        predictions = []
        for day in range(1, self.LOOKAHEAD_DAYS + 1):
            predicted_arrivals = self._forecast_arrivals(day, arrival_rate)
            predicted_capacity = self._forecast_capacity(day, service_rate)
            
            queue_backlog += predicted_arrivals - predicted_capacity
            queue_backlog = max(0.0, queue_backlog)
            
            utilization = (predicted_arrivals / max(predicted_capacity, 0.01))
            
            predictions.append(BottleneckPrediction(
                day=day,
                arrivals=round(predicted_arrivals, 1),
                capacity=round(predicted_capacity, 1),
                queue_length=round(queue_backlog, 1),
                utilization=min(utilization, 2.0),
                is_bottleneck=queue_backlog > self.THRESHOLD_QUEUE_LENGTH
            ))
        
        return predictions
    
    def _forecast_arrivals(self, day: int, base_rate: float) -> float:
        """Forecast arrivals with weekly seasonality."""
        day_of_week = (datetime.now() + timedelta(days=day)).weekday()
        # Fewer arrivals on weekends
        weekend_factor = 0.3 if day_of_week >= 5 else 1.0
        noise = random.gauss(0.0, 0.15 * base_rate)
        return max(0, base_rate * weekend_factor + noise)
    
    def _forecast_capacity(self, day: int, base_rate: float) -> float:
        """Forecast checking capacity with known patterns."""
        day_of_week = (datetime.now() + timedelta(days=day)).weekday()
        weekend_factor = 0.0 if day_of_week >= 5 else 1.0
        noise = random.gauss(0.0, 0.1 * base_rate)
        return max(0, base_rate * weekend_factor + noise)
    
    def run_what_if(self, scenario_type: str, params: dict) -> dict:
        """Run a what-if scenario simulation."""
        # Delegate to scenario-specific handlers
        handlers = {
            'reassign': self._scenario_reassign,
            'shift_dates': self._scenario_shift_dates,
            'add_resource': self._scenario_add_resource,
        }
        handler = handlers.get(scenario_type)
        if not handler:
            return {'error': f'Unknown scenario: {scenario_type}'}
        return handler(params)
    
    def _scenario_reassign(self, params: dict) -> dict:
        """Simulate reassigning units to a different detailer."""
        return {
            'scenario': 'reassign',
            'description': f"Reassign {len(params.get('unit_ids', []))} units to {params.get('target_detailer')}",
            'simulated_impacts': self._compute_reassignment_impact(
                params['unit_ids'],
                params['target_detailer']
            )
        }
    
    def _scenario_shift_dates(self, params: dict) -> dict:
        """Simulate shifting due dates."""
        return {
            'scenario': 'shift_dates',
            'description': f"Shift due dates for {len(params.get('unit_ids', []))} units",
            'simulated_impacts': {'new_risk_scores': 'computed_per_unit'}
        }
    
    def _scenario_add_resource(self, params: dict) -> dict:
        """Simulate adding checking capacity."""
        capacity_add = params.get('additional_capacity', 0)
        return {
            'scenario': 'add_resource',
            'description': f"Add {capacity_add} units/day checking capacity",
            'simulated_impacts': {
                'queue_reduction_days': self._estimate_queue_reduction(capacity_add)
            }
        }
    
    def _compute_reassignment_impact(self, unit_ids: list[str], 
                                      target_detailer: str) -> dict:
        """Compute the impact of reassignment on risk scores."""
        # Simplified implementation for MVP
        return {'status': 'simulated', 'details': 'pending'}
    
    def _estimate_queue_reduction(self, additional_capacity: float) -> float:
        """Estimate days to clear current queue with added capacity."""
        current_queue = self._data.get_current_checking_queue_length()
        daily_capacity = self._data.get_daily_checking_capacity()
        daily_arrivals = mean(self._data.get_arrivals_last_n_days(30))
        
        net_throughput = (daily_capacity + additional_capacity) - daily_arrivals
        if net_throughput <= 0:
            return float('inf')
        return current_queue / net_throughput
    
    @staticmethod
    def _score_to_label(score: float) -> str:
        if score < 0:
            return "insufficient-data"
        if score <= 0.20:
            return "low"
        if score <= 0.40:
            return "moderate"
        if score <= 0.60:
            return "elevated"
        if score <= 0.80:
            return "high"
        return "critical"
    
    @staticmethod
    def linear_regression(x: list[float], y: list[float]) -> tuple[float, float]:
        """Simple linear regression: returns (slope, intercept)."""
        n = len(x)
        if n < 2:
            return (0.0, mean(y) if y else 0.0)
        x_mean = mean(x)
        y_mean = mean(y)
        num = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
        den = sum((xi - x_mean) ** 2 for xi in x)
        slope = num / den if den != 0 else 0.0
        intercept = y_mean - slope * x_mean
        return (slope, intercept)
```

---

## Implementation Phases

### Phase 1: Risk Scoring Engine (5 days)
1. Implement `AnalyticsEngine` base class with data provider abstraction
2. Implement Monte Carlo risk scoring with bootstrap resampling
3. Implement risk score label classification
4. Implement confidence interval computation
5. **Tests**: Property-based tests verifying risk score bounds and distribution shape

### Phase 2: Workload & Bottleneck Forecasting (4 days)
1. Implement weighted moving average workload forecast
2. Implement day-of-week seasonality adjustment
3. Implement M/M/1 queueing model for checking pipeline
4. Implement bottleneck detection with configurable thresholds
5. **Tests**: Test forecast accuracy against historical data (backtesting)

### Phase 3: What-If Scenarios (4 days)
1. Implement reassignment scenario handler
2. Implement date-shift scenario handler
3. Implement resource-addition scenario handler
4. Implement scenario comparison output (delta from baseline)
5. **Tests**: Test scenario handlers with known inputs verify expected outputs

### Phase 4: Trend Dashboards (3 days)
1. Implement data aggregation for trend metrics
2. Implement dashboard widget components (line, bar, area, gauge, heatmap)
3. Implement time range selector (1mo/3mo/6mo)
4. Wire analytics engine into the main application
5. **Tests**: Integration test verifying dashboard renders with real data

---

## Success Criteria

1. Risk score correctly correlates with actual on-time completion rate (verify with historical data, target correlation >0.7)
2. Workload forecast accuracy within ±25% for 30-day projections
3. Bottleneck predictions identify at least 80% of actual queue buildups
4. What-if scenarios compute results within 2 seconds for typical data sets
5. Dashboards render with <500ms latency for all metrics
6. All analytics operate on datasets of 10,000+ units without memory issues

---

## Formulas Reference

### Monte Carlo Risk Score

```
P(on_time) = (1/N) * Σᵢ₌₁ᴺ I(C + Tᵢ * (1-p) ≤ D)

where:
  N = number of simulations (10,000)
  C = current date
  Tᵢ = bootstrapped completion time from history
  p = percent complete (0.0 to 1.0)
  D = due date
  I(·) = indicator function (1 if true, 0 otherwise)
```

### Exponential Moving Average (Forecast)

```
Fₜ = α * Xₜ + (1-α) * Fₜ₋₁

where:
  Fₜ = forecast at time t
  Xₜ = actual value at time t
  α = smoothing factor (default: 0.3)
```

### M/M/1 Queue Metrics

```
ρ = λ / μ                          (utilization)
L = ρ / (1-ρ)                       (avg units in system)
Lq = ρ² / (1-ρ)                     (avg units in queue)
W = 1 / (μ - λ)                     (avg time in system)
Wq = ρ / (μ - λ)                    (avg time in queue)
P(n) = (1-ρ) * ρⁿ                   (probability of n units)
```

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Insufficient historical data for meaningful simulations | Medium | Fall back to heuristic rules when < MIN_SAMPLES; show "insufficient data" label |
| Forecast drift over longer horizons | High | Display confidence intervals; limit forecasts to 30-day horizon with disclaimer |
| What-if scenarios give false confidence | Medium | Always show baseline comparison; mark simulated results as projections |
| Performance of Monte Carlo for large datasets | Low | Vectorize with numpy if needed; cache intermediate results |
| Users misuse predictive outputs as guarantees | Medium | Add UI disclaimers; show uncertainty explicitly with confidence intervals |

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: Risk Scoring Engine | 5 |
| Phase 2: Workload & Bottleneck Forecasting | 4 |
| Phase 3: What-If Scenarios | 4 |
| Phase 4: Trend Dashboards | 3 |
| **Total** | **16** |
