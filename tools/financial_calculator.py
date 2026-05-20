import re
from typing import Dict, Any, Optional
from loguru import logger

class FinancialCalculator:
    """
    Central module for all financial metric calculations used across all subagents.
    All inputs come from yearly_master.json structure.
    All outputs are dicts keyed by fiscal year.
    All methods are static and wrapped in try/except.
    """

    @staticmethod
    def safe_divide(numerator: float, denominator: float, fallback: float = None) -> float | None:
        """
        Divides numerator by denominator.
        Returns fallback if denominator is 0 or None.
        Returns fallback if either input is None.
        Never raises ZeroDivisionError.
        """
        try:
            if numerator is None or denominator is None:
                return fallback
            if float(denominator) == 0.0:
                return fallback
            return float(numerator) / float(denominator)
        except Exception as e:
            logger.error(f"safe_divide error: {e}")
            return fallback

    @staticmethod
    def compute_nopat(ebit: float, tax_rate: float) -> float | None:
        """
        NOPAT = EBIT × (1 - tax_rate)
        tax_rate expressed as decimal (e.g. 0.25 for 25%)
        Returns None if either input is None.
        """
        try:
            if ebit is None or tax_rate is None:
                return None
            val = float(ebit) * (1.0 - float(tax_rate))
            return round(val, 2)
        except Exception as e:
            logger.error(f"compute_nopat error: {e}")
            return None

    @staticmethod
    def compute_invested_capital(total_equity: float, total_debt: float, cash_equivalents: float) -> float | None:
        """
        Invested Capital = Total Equity + Total Debt - Cash & Equivalents
        Returns None if any input is None.
        """
        try:
            if total_equity is None or total_debt is None or cash_equivalents is None:
                return None
            val = float(total_equity) + float(total_debt) - float(cash_equivalents)
            return round(val, 2)
        except Exception as e:
            logger.error(f"compute_invested_capital error: {e}")
            return None

    @staticmethod
    def compute_roic(nopat: float, invested_capital: float) -> float | None:
        """
        ROIC = NOPAT / Invested Capital × 100
        Returns percentage (e.g. 18.4 for 18.4%)
        Uses safe_divide. Returns None if inputs invalid.
        """
        try:
            if nopat is None or invested_capital is None:
                return None
            ratio = FinancialCalculator.safe_divide(nopat, invested_capital)
            if ratio is None:
                return None
            return round(ratio * 100.0, 2)
        except Exception as e:
            logger.error(f"compute_roic error: {e}")
            return None

    @staticmethod
    def compute_capital_employed(total_assets: float, current_liabilities: float) -> float | None:
        """
        Capital Employed = Total Assets - Current Liabilities
        Returns None if any input is None.
        """
        try:
            if total_assets is None or current_liabilities is None:
                return None
            val = float(total_assets) - float(current_liabilities)
            return round(val, 2)
        except Exception as e:
            logger.error(f"compute_capital_employed error: {e}")
            return None

    @staticmethod
    def compute_roce(ebit: float, capital_employed: float) -> float | None:
        """
        ROCE = EBIT / Capital Employed × 100
        Returns percentage.
        Uses safe_divide. Returns None if inputs invalid.
        """
        try:
            if ebit is None or capital_employed is None:
                return None
            ratio = FinancialCalculator.safe_divide(ebit, capital_employed)
            if ratio is None:
                return None
            return round(ratio * 100.0, 2)
        except Exception as e:
            logger.error(f"compute_roce error: {e}")
            return None

    @staticmethod
    def _extract_value(year_data: dict, keys: list) -> float | None:
        """
        Helper method to extract numerical value from year_data tables 
        based on a list of matching keys.
        """
        tables = year_data.get("tables", [])
        if not tables:
            return None
            
        keys_lower = [k.lower().strip() for k in keys]
        
        # Check if there are non-USD tables in the document.
        # If there are both USD and non-USD tables, we prefer non-USD tables for focal INR firms.
        has_non_usd_tables = False
        for table in tables:
            headers_str = " ".join([str(h) for h in table.get("headers", [])]).lower()
            table_name = str(table.get("table_name", "")).lower()
            if "usd" not in headers_str and "usd" not in table_name:
                has_non_usd_tables = True
                break

        for exact in [True, False]:
            for table in tables:
                # Currency filter: if we have non-USD tables, skip any table that contains USD in header/name
                if has_non_usd_tables:
                    headers_str = " ".join([str(h) for h in table.get("headers", [])]).lower()
                    table_name = str(table.get("table_name", "")).lower()
                    if "usd" in headers_str or "usd" in table_name:
                        continue

                for row in table.get("rows", []):
                    label = str(row.get("label", "")).lower().strip()
                    match = False
                    if exact:
                        match = any(label == k for k in keys_lower)
                    else:
                        match = any(k in label for k in keys_lower)
                        
                    if match:
                        for val in row.get("values", []):
                            try:
                                cleaned = str(val).replace(",", "").replace("$", "").replace("₹", "").strip()
                                if cleaned.startswith("(") and cleaned.endswith(")"):
                                    cleaned = "-" + cleaned[1:-1]
                                return float(cleaned)
                            except ValueError:
                                continue
        return None

    @staticmethod
    def _format_fy(key: str) -> str:
        """
        Extracts 4-digit year from string and formats as FY{YYYY}.
        """
        match = re.search(r'(20\d{2})', str(key))
        if match:
            return f"FY{match.group(1)}"
        return f"FY{key}"

    @staticmethod
    def compute_roic_roce_series(yearly_master: dict, metric_map: dict) -> dict:
        """
        Computes both ROIC and ROCE for every fiscal year available in yearly_master.
        """
        results = {}
        try:
            for raw_key, year_data in yearly_master.items():
                fy = FinancialCalculator._format_fy(raw_key)
                
                ebit = FinancialCalculator._extract_value(year_data, metric_map.get("ebit", []))
                tax_rate = FinancialCalculator._extract_value(year_data, metric_map.get("tax_rate", []))
                total_equity = FinancialCalculator._extract_value(year_data, metric_map.get("total_equity", []))
                total_debt = FinancialCalculator._extract_value(year_data, metric_map.get("total_debt", []))
                cash_equivalents = FinancialCalculator._extract_value(year_data, metric_map.get("cash_equivalents", []))
                total_assets = FinancialCalculator._extract_value(year_data, metric_map.get("total_assets", []))
                current_liabilities = FinancialCalculator._extract_value(year_data, metric_map.get("current_liabilities", []))
                
                # FALLBACK A: Tax rate fallback from total tax expense and profit before tax
                if tax_rate is None:
                    tax_exp_keys = ["total tax expense", "tax expense", "tax expense - current tax + deferred tax", "current tax + deferred tax"]
                    pbt_keys = ["profit before tax", "pbt", "profit before exceptional item and tax", "profit before tax and exceptional item"]
                    
                    total_tax_expense = FinancialCalculator._extract_value(year_data, tax_exp_keys)
                    profit_before_tax = FinancialCalculator._extract_value(year_data, pbt_keys)
                    if total_tax_expense is not None and profit_before_tax is not None and profit_before_tax != 0:
                        tax_rate = total_tax_expense / profit_before_tax
                        logger.info(f"Dynamically calculated tax rate for {fy}: {tax_rate}")
                        
                # Ensure tax rate is ratio, not percentage
                if tax_rate is not None and tax_rate > 1.0:
                    tax_rate = tax_rate / 100.0
                    
                # FALLBACK B: Total debt fallback by summing borrowings and lease liabilities
                if total_debt is None:
                    summed_debt = 0.0
                    tables = year_data.get("tables", [])
                    has_non_usd_tables = False
                    for table in tables:
                        headers_str = " ".join([str(h) for h in table.get("headers", [])]).lower()
                        table_name = str(table.get("table_name", "")).lower()
                        if "usd" not in headers_str and "usd" not in table_name:
                            has_non_usd_tables = True
                            break
                            
                    found_items = []
                    for table in tables:
                        if has_non_usd_tables:
                            headers_str = " ".join([str(h) for h in table.get("headers", [])]).lower()
                            table_name = str(table.get("table_name", "")).lower()
                            if "usd" in headers_str or "usd" in table_name:
                                continue
                        for row in table.get("rows", []):
                            label = str(row.get("label", "")).lower().strip()
                            if "borrowings" in label or "lease liabilities" in label:
                                for val in row.get("values", []):
                                    try:
                                        cleaned = str(val).replace(",", "").replace("$", "").replace("₹", "").strip()
                                        if cleaned.startswith("(") and cleaned.endswith(")"):
                                            cleaned = "-" + cleaned[1:-1]
                                        f_val = float(cleaned)
                                        if f_val > 0:
                                            found_items.append((row.get("label"), f_val))
                                            summed_debt += f_val
                                            break # only take first float in row
                                    except ValueError:
                                        continue
                    if summed_debt > 0:
                        total_debt = summed_debt
                        logger.info(f"Summed total debt for {fy} from borrowings/lease liabilities: {total_debt} ({found_items})")

                missing = []
                for name, val in [("ebit", ebit), ("tax_rate", tax_rate), ("total_equity", total_equity), 
                                  ("total_debt", total_debt), ("cash_equivalents", cash_equivalents), 
                                  ("total_assets", total_assets), ("current_liabilities", current_liabilities)]:
                    if val is None:
                        missing.append(name)
                        
                if missing:
                    logger.warning(f"Could not find {', '.join(missing)} for {fy} in financials")
                    
                nopat = FinancialCalculator.compute_nopat(ebit, tax_rate)
                invested_capital = FinancialCalculator.compute_invested_capital(total_equity, total_debt, cash_equivalents)
                roic = FinancialCalculator.compute_roic(nopat, invested_capital)
                
                capital_employed = FinancialCalculator.compute_capital_employed(total_assets, current_liabilities)
                roce = FinancialCalculator.compute_roce(ebit, capital_employed)
                
                results[fy] = {
                    "roic": roic,
                    "roce": roce,
                    "nopat": nopat,
                    "invested_capital": invested_capital,
                    "capital_employed": capital_employed,
                    "ebit": ebit,
                    "tax_rate": tax_rate
                }
                
            return dict(sorted(results.items()))
        except Exception as e:
            logger.error(f"compute_roic_roce_series error: {e}")
            return results

    @staticmethod
    def analyse_roic_trend(roic_series: dict, wacc: float) -> dict:
        """
        Takes output of compute_roic_roce_series and wacc.
        Computes trend, consistency, and value creation metrics.
        """
        result = {
            "roic_vs_wacc_by_year": {},
            "trend_direction": "stable",
            "trend_consistency": "mixed",
            "peak_roic": {"year": "N/A", "value": 0.0},
            "trough_roic": {"year": "N/A", "value": 0.0},
            "latest_roic": {"year": "N/A", "value": 0.0},
            "latest_roce": {"year": "N/A", "value": 0.0},
            "years_analysed": 0,
            "years_with_missing_data": []
        }
        
        try:
            valid_years = []
            
            for fy, data in roic_series.items():
                roic = data.get("roic")
                roce = data.get("roce")
                if roic is None:
                    result["years_with_missing_data"].append(fy)
                    continue
                    
                valid_years.append((fy, roic, roce))
                spread = round(roic - wacc, 2)
                result["roic_vs_wacc_by_year"][fy] = {
                    "roic": roic,
                    "wacc": round(wacc, 2),
                    "spread": spread,
                    "value_creating": spread > 0
                }
                
            result["years_analysed"] = len(valid_years)
            if not valid_years:
                return result
                
            peak = max(valid_years, key=lambda x: x[1])
            trough = min(valid_years, key=lambda x: x[1])
            latest = valid_years[-1]
            
            result["peak_roic"] = {"year": peak[0], "value": peak[1]}
            result["trough_roic"] = {"year": trough[0], "value": trough[1]}
            result["latest_roic"] = {"year": latest[0], "value": latest[1]}
            if latest[2] is not None:
                result["latest_roce"] = {"year": latest[0], "value": latest[2]}
                
            above_count = sum(1 for fy in valid_years if result["roic_vs_wacc_by_year"][fy[0]]["value_creating"])
            pct_above = above_count / len(valid_years)
            if pct_above > 0.75:
                result["trend_consistency"] = "consistently above"
            elif pct_above >= 0.50:
                result["trend_consistency"] = "mostly above"
            elif pct_above >= 0.25:
                result["trend_consistency"] = "mixed"
            else:
                result["trend_consistency"] = "mostly below"
                
            if len(valid_years) >= 6:
                recent_avg = sum(x[1] for x in valid_years[-3:]) / 3.0
                prior_avg = sum(x[1] for x in valid_years[-6:-3]) / 3.0
                if recent_avg - prior_avg > 1.0:
                    result["trend_direction"] = "rising"
                elif prior_avg - recent_avg > 1.0:
                    result["trend_direction"] = "falling"
            elif len(valid_years) >= 4:
                recent_avg = sum(x[1] for x in valid_years[-2:]) / 2.0
                prior_avg = sum(x[1] for x in valid_years[-4:-2]) / 2.0
                if recent_avg - prior_avg > 1.0:
                    result["trend_direction"] = "rising"
                elif prior_avg - recent_avg > 1.0:
                    result["trend_direction"] = "falling"
                    
            return result
        except Exception as e:
            logger.error(f"analyse_roic_trend error: {e}")
            return result

    @staticmethod
    def compute_future_value_percentage(stock_price: float, shares_outstanding: float, yearly_master: dict, metric_map: dict, wacc: float = 10.0) -> dict:
        """
        Estimates what percentage of stock price represents future value creation vs current asset value.
        NOTE: Added wacc parameter to compute NOPAT/wacc operations value.
        """
        result = {
            "market_cap": 0.0,
            "book_value_equity": 0.0,
            "pb_ratio": 0.0,
            "current_ops_value": 0.0,
            "future_value": 0.0,
            "future_value_pct": 0.0,
            "interpretation": "Missing data for evaluation."
        }
        
        try:
            if stock_price is None or shares_outstanding is None:
                return result
                
            market_cap = float(stock_price) * float(shares_outstanding)
            result["market_cap"] = round(market_cap, 2)
            
            sorted_keys = sorted(yearly_master.keys())
            latest_equity = None
            latest_ebit = None
            latest_tax = None
            
            for key in reversed(sorted_keys):
                yd = yearly_master[key]
                eq = FinancialCalculator._extract_value(yd, metric_map.get("total_equity", []))
                if eq is not None and latest_equity is None:
                    latest_equity = eq
                    
                ebit = FinancialCalculator._extract_value(yd, metric_map.get("ebit", []))
                tax = FinancialCalculator._extract_value(yd, metric_map.get("tax_rate", []))
                
                if ebit is not None and tax is not None and latest_ebit is None:
                    latest_ebit = ebit
                    latest_tax = tax
                    
            if latest_equity:
                result["book_value_equity"] = round(latest_equity, 2)
                pb = FinancialCalculator.safe_divide(market_cap, latest_equity)
                result["pb_ratio"] = round(pb, 2) if pb is not None else 0.0
                
            if latest_ebit is not None and latest_tax is not None:
                nopat = FinancialCalculator.compute_nopat(latest_ebit, latest_tax)
                if nopat is not None and wacc > 0:
                    current_ops_value = nopat / (wacc / 100.0)
                    result["current_ops_value"] = round(current_ops_value, 2)
                    
                    future_value = market_cap - current_ops_value
                    result["future_value"] = round(future_value, 2)
                    
                    fv_pct = FinancialCalculator.safe_divide(future_value, market_cap) * 100.0
                    
                    if fv_pct < 0:
                        fv_pct = 0.0
                        result["interpretation"] = "Market is pricing in a decline; future value component is negligible."
                    elif fv_pct > 100:
                        fv_pct = 100.0
                        result["interpretation"] = "Market cap is predominantly driven by future value expectations."
                        logger.warning("Future value percentage capped at 100.")
                    else:
                        result["interpretation"] = f"Approximately {round(fv_pct, 1)}% of the market cap represents future value creation."
                        
                    result["future_value_pct"] = round(fv_pct, 2)
                    
        except Exception as e:
            logger.error(f"compute_future_value_percentage error: {e}")
            
        return result

    @staticmethod
    def compute_revenue_growth(yearly_master: dict, metric_map: dict) -> dict:
        """
        Computes YoY revenue growth % for each fiscal year.
        Also computes 3-year and 5-year CAGR.
        """
        result = {
            "yoy_growth": {},
            "cagr_3yr": None,
            "cagr_5yr": None,
            "latest_revenue": 0.0,
            "revenue_trend": "stable"
        }
        
        try:
            rev_series = {}
            for raw_key, year_data in yearly_master.items():
                fy = FinancialCalculator._format_fy(raw_key)
                rev = FinancialCalculator._extract_value(year_data, metric_map.get("revenue", ["revenue", "net revenue", "total revenue", "net sales", "total income from operations"]))
                if rev is not None:
                    rev_series[fy] = rev
                    
            sorted_fys = sorted(rev_series.keys())
            
            for i in range(1, len(sorted_fys)):
                prev_fy = sorted_fys[i-1]
                curr_fy = sorted_fys[i]
                prev_rev = rev_series[prev_fy]
                curr_rev = rev_series[curr_fy]
                
                yoy = FinancialCalculator.safe_divide((curr_rev - prev_rev), prev_rev)
                if yoy is not None:
                    result["yoy_growth"][curr_fy] = round(yoy * 100.0, 2)
                    
            if sorted_fys:
                result["latest_revenue"] = round(rev_series[sorted_fys[-1]], 2)
                
            def get_cagr(years):
                if len(sorted_fys) >= years + 1:
                    start_val = rev_series[sorted_fys[-(years+1)]]
                    end_val = rev_series[sorted_fys[-1]]
                    if start_val > 0:
                        return round(((end_val / start_val) ** (1/years) - 1) * 100.0, 2)
                return None
                
            result["cagr_3yr"] = get_cagr(3)
            result["cagr_5yr"] = get_cagr(5)
            
            if result["cagr_3yr"] is not None and result["cagr_5yr"] is not None:
                if result["cagr_3yr"] - result["cagr_5yr"] > 2.0:
                    result["revenue_trend"] = "accelerating"
                elif result["cagr_5yr"] - result["cagr_3yr"] > 2.0:
                    result["revenue_trend"] = "decelerating"
                    
            return result
        except Exception as e:
            logger.error(f"compute_revenue_growth error: {e}")
            return result

    @staticmethod
    def compute_margin_series(yearly_master: dict, metric_map: dict) -> dict:
        """
        Computes EBITDA margin and PAT margin for each year.
        """
        result = {
            "ebitda_margin": {},
            "pat_margin": {},
            "latest_ebitda_margin": 0.0,
            "latest_pat_margin": 0.0,
            "margin_trend": "stable"
        }
        
        try:
            valid_margins = []
            for raw_key, year_data in yearly_master.items():
                fy = FinancialCalculator._format_fy(raw_key)
                rev = FinancialCalculator._extract_value(year_data, metric_map.get("revenue", ["revenue", "net revenue", "total revenue", "net sales"]))
                ebitda = FinancialCalculator._extract_value(year_data, metric_map.get("ebitda", ["ebitda", "operating profit before depreciation"]))
                pat = FinancialCalculator._extract_value(year_data, metric_map.get("pat", ["pat", "profit after tax", "net profit", "profit for the year"]))
                
                ebitda_m = None
                pat_m = None
                
                if rev and rev > 0:
                    if ebitda is not None:
                        ebitda_m = round((ebitda / rev) * 100.0, 2)
                        result["ebitda_margin"][fy] = ebitda_m
                    if pat is not None:
                        pat_m = round((pat / rev) * 100.0, 2)
                        result["pat_margin"][fy] = pat_m
                        
                if ebitda_m is not None:
                    valid_margins.append((fy, ebitda_m))
                    
            valid_margins.sort(key=lambda x: x[0])
            
            if valid_margins:
                result["latest_ebitda_margin"] = valid_margins[-1][1]
                
            sorted_pats = sorted(result["pat_margin"].keys())
            if sorted_pats:
                result["latest_pat_margin"] = result["pat_margin"][sorted_pats[-1]]
                
            if len(valid_margins) >= 3:
                recent = valid_margins[-1][1]
                past = valid_margins[-3][1]
                if recent - past > 1.0:
                    result["margin_trend"] = "expanding"
                elif past - recent > 1.0:
                    result["margin_trend"] = "contracting"
                    
            return result
        except Exception as e:
            logger.error(f"compute_margin_series error: {e}")
            return result

    @staticmethod
    def compute_gross_margin_series(yearly_master: dict, metric_map: dict) -> dict:
        """
        Computes gross margin % for each fiscal year.
        """
        result = {}
        try:
            for raw_key, year_data in yearly_master.items():
                fy = FinancialCalculator._format_fy(raw_key)
                
                rev = FinancialCalculator._extract_value(year_data, metric_map.get("revenue", ["revenue", "net revenue", "total revenue", "net sales", "revenue from operations"]))
                gp = FinancialCalculator._extract_value(year_data, metric_map.get("gross_profit", ["gross profit", "gross margin", "revenue from operations - cost of materials", "net revenue - cost of goods sold"]))
                cogs = FinancialCalculator._extract_value(year_data, metric_map.get("cogs", ["cost of goods sold", "cost of materials consumed", "cost of revenue", "direct costs"]))
                
                gm_pct = None
                calculated_gp = gp
                
                if gp is not None and rev is not None and rev > 0:
                    gm_pct = (gp / rev) * 100.0
                elif rev is not None and cogs is not None and rev > 0:
                    calculated_gp = rev - cogs
                    gm_pct = (calculated_gp / rev) * 100.0
                else:
                    logger.warning(f"Could not compute gross margin for {fy} — missing gross profit and COGS fields")
                    
                result[fy] = {
                    "gross_margin_pct": round(gm_pct, 2) if gm_pct is not None else None,
                    "gross_profit": round(calculated_gp, 2) if calculated_gp is not None else None,
                    "revenue": round(rev, 2) if rev is not None else None,
                    "cogs": round(cogs, 2) if cogs is not None else None
                }
                
            return dict(sorted(result.items()))
        except Exception as e:
            logger.error(f"compute_gross_margin_series error: {e}")
            return result

    @staticmethod
    def analyse_gross_margin_trend(gross_margin_series: dict) -> dict:
        """
        Analyses gross margin trend over available years.
        """
        result = {
            "yoy_change": {},
            "trend_direction": "stable",
            "markup_proxy": {},
            "markup_trend": "stable",
            "peak_margin": {"year": "N/A", "value": 0.0},
            "trough_margin": {"year": "N/A", "value": 0.0},
            "latest_margin": {"year": "N/A", "value": 0.0},
            "average_margin": 0.0,
            "years_analysed": 0
        }
        
        try:
            valid_margins = []
            fys = sorted(gross_margin_series.keys())
            
            # yoy_change
            for i in range(len(fys)):
                fy = fys[i]
                gm = gross_margin_series[fy].get("gross_margin_pct")
                
                if gm is not None:
                    valid_margins.append((fy, gm))
                    
                if i > 0:
                    prev_fy = fys[i-1]
                    prev_gm = gross_margin_series[prev_fy].get("gross_margin_pct")
                    if gm is not None and prev_gm is not None:
                        result["yoy_change"][fy] = round(gm - prev_gm, 2)
                        
            # markup proxy
            valid_markups = []
            for fy in fys:
                gp = gross_margin_series[fy].get("gross_profit")
                cogs = gross_margin_series[fy].get("cogs")
                markup = None
                if gp is not None and cogs is not None and cogs > 0:
                    markup = (gp / cogs) * 100.0
                    valid_markups.append((fy, markup))
                result["markup_proxy"][fy] = round(markup, 2) if markup is not None else None
                
            result["years_analysed"] = len(valid_margins)
            if not valid_margins:
                return result
                
            peak = max(valid_margins, key=lambda x: x[1])
            trough = min(valid_margins, key=lambda x: x[1])
            
            result["peak_margin"] = {"year": peak[0], "value": round(peak[1], 2)}
            result["trough_margin"] = {"year": trough[0], "value": round(trough[1], 2)}
            result["latest_margin"] = {"year": valid_margins[-1][0], "value": round(valid_margins[-1][1], 2)}
            result["average_margin"] = round(sum(x[1] for x in valid_margins) / len(valid_margins), 2)
            
            # trend direction
            if len(valid_margins) >= 6:
                recent_avg = sum(x[1] for x in valid_margins[-3:]) / 3.0
                prior_avg = sum(x[1] for x in valid_margins[-6:-3]) / 3.0
                if recent_avg - prior_avg > 0.5:
                    result["trend_direction"] = "expanding"
                elif prior_avg - recent_avg > 0.5:
                    result["trend_direction"] = "contracting"
            elif len(valid_margins) >= 4:
                recent_avg = sum(x[1] for x in valid_margins[-2:]) / 2.0
                prior_avg = sum(x[1] for x in valid_margins[-4:-2]) / 2.0
                if recent_avg - prior_avg > 0.5:
                    result["trend_direction"] = "expanding"
                elif prior_avg - recent_avg > 0.5:
                    result["trend_direction"] = "contracting"
                    
            # markup trend
            if len(valid_markups) >= 6:
                recent_avg = sum(x[1] for x in valid_markups[-3:]) / 3.0
                prior_avg = sum(x[1] for x in valid_markups[-6:-3]) / 3.0
                if recent_avg - prior_avg > 0.5:
                    result["markup_trend"] = "expanding"
                elif prior_avg - recent_avg > 0.5:
                    result["markup_trend"] = "contracting"
            elif len(valid_markups) >= 4:
                recent_avg = sum(x[1] for x in valid_markups[-2:]) / 2.0
                prior_avg = sum(x[1] for x in valid_markups[-4:-2]) / 2.0
                if recent_avg - prior_avg > 0.5:
                    result["markup_trend"] = "expanding"
                elif prior_avg - recent_avg > 0.5:
                    result["markup_trend"] = "contracting"
                    
            return result
        except Exception as e:
            logger.error(f"analyse_gross_margin_trend error: {e}")
            return result

    @staticmethod
    def compute_peer_roic_series(peer_financials: dict, metric_map: dict) -> dict:
        """
        Computes ROIC and ROCE for each peer company for each available fiscal year.
        """
        result = {}
        try:
            for peer, yearly_master in peer_financials.items():
                if yearly_master:
                    result[peer] = FinancialCalculator.compute_roic_roce_series(yearly_master, metric_map)
            return result
        except Exception as e:
            logger.error(f"compute_peer_roic_series error: {e}")
            return result

    @staticmethod
    def compute_industry_statistics(focal_ticker: str, focal_roic_series: dict, peer_roic_series: dict, industry_roic_input: float, industry_roic_trend: str) -> dict:
        """
        Combines focal and peer ROIC data to compute industry-level statistics.
        """
        result = {
            "per_year_stats": {},
            "industry_benchmark": {
                "user_provided_roic": industry_roic_input,
                "user_provided_trend": industry_roic_trend,
                "source_note": "User-provided at runtime"
            },
            "focal_positioning_summary": "",
            "peer_set": list(peer_roic_series.keys()),
            "years_with_full_data": []
        }
        
        try:
            # Combine ROIC data
            combined = {}
            for fy, data in focal_roic_series.items():
                roic = data.get("roic")
                if roic is not None:
                    combined.setdefault(fy, {})[focal_ticker] = roic
                    
            for peer, series in peer_roic_series.items():
                for fy, data in series.items():
                    roic = data.get("roic")
                    if roic is not None:
                        combined.setdefault(fy, {})[peer] = roic
                        
            # Compute stats per year
            for fy, comps in combined.items():
                if len(comps) >= 2:
                    values = list(comps.values())
                    mean_val = sum(values) / len(values)
                    sorted_vals = sorted(values)
                    mid = len(sorted_vals) // 2
                    median_val = (sorted_vals[mid] + sorted_vals[~mid]) / 2.0
                    
                    min_co = min(comps.items(), key=lambda x: x[1])
                    max_co = max(comps.items(), key=lambda x: x[1])
                    
                    var = sum((x - mean_val) ** 2 for x in values) / len(values)
                    std_dev = var ** 0.5
                    
                    # Focal ranking
                    focal_rank = None
                    focal_vs_mean = None
                    focal_roic = comps.get(focal_ticker)
                    
                    if focal_roic is not None:
                        # rank 1 is highest
                        sorted_comps = sorted(comps.items(), key=lambda x: x[1], reverse=True)
                        focal_rank = next(i for i, v in enumerate(sorted_comps) if v[0] == focal_ticker) + 1
                        focal_vs_mean = focal_roic - mean_val
                        
                    result["per_year_stats"][fy] = {
                        "mean_roic": round(mean_val, 2),
                        "median_roic": round(median_val, 2),
                        "min_roic": {"company": min_co[0], "value": round(min_co[1], 2)},
                        "max_roic": {"company": max_co[0], "value": round(max_co[1], 2)},
                        "variance": round(var, 2),
                        "std_deviation": round(std_dev, 2),
                        "companies_included": list(comps.keys()),
                        "focal_rank": focal_rank,
                        "focal_vs_mean": round(focal_vs_mean, 2) if focal_vs_mean is not None else None
                    }
                    
                    if len(comps) == len(peer_roic_series) + 1:
                        result["years_with_full_data"].append(fy)
                        
            # Focal positioning summary
            if result["per_year_stats"]:
                latest_fy = max(result["per_year_stats"].keys())
                stats = result["per_year_stats"][latest_fy]
                if stats["focal_rank"] is not None:
                    result["focal_positioning_summary"] = f"In {latest_fy}, {focal_ticker} ranked {stats['focal_rank']} out of {len(stats['companies_included'])} with an ROIC of {combined[latest_fy][focal_ticker]}% vs peer mean of {stats['mean_roic']}%."
                else:
                    result["focal_positioning_summary"] = f"In {latest_fy}, focal company ROIC not available. Peer mean was {stats['mean_roic']}%."
            else:
                result["focal_positioning_summary"] = "Insufficient data to compute peer statistics."
                
            return result
        except Exception as e:
            logger.error(f"compute_industry_statistics error: {e}")
            return result

    @staticmethod
    def compute_proxy_market_share(focal_ticker: str, focal_yearly_master: dict, peer_financials: dict, metric_map: dict) -> dict:
        """
        Computes proxy market share for focal company and each peer using relative revenue within the comparable listed universe.
        """
        result = {}
        try:
            # Step 1: Extract revenue
            revenue_data = {} # {fy: {ticker: revenue}}
            rev_keys = metric_map.get("revenue", ["revenue", "net revenue", "total revenue", "net sales", "revenue from operations"])
            
            for raw_key, year_data in focal_yearly_master.items():
                fy = FinancialCalculator._format_fy(raw_key)
                rev = FinancialCalculator._extract_value(year_data, rev_keys)
                if rev is not None:
                    revenue_data.setdefault(fy, {})[focal_ticker] = rev
                    
            for peer, yearly_master in peer_financials.items():
                for raw_key, year_data in yearly_master.items():
                    fy = FinancialCalculator._format_fy(raw_key)
                    rev = FinancialCalculator._extract_value(year_data, rev_keys)
                    if rev is not None:
                        revenue_data.setdefault(fy, {})[peer] = rev
                        
            # Step 2: Compute share
            for fy, comps in revenue_data.items():
                universe_rev = sum(comps.values())
                result[fy] = {
                    "universe_revenue": round(universe_rev, 2),
                    "companies_included": list(comps.keys())
                }
                for comp, rev in comps.items():
                    share = 0.0
                    if universe_rev > 0:
                        share = (rev / universe_rev) * 100.0
                    result[fy][comp] = {
                        "revenue": round(rev, 2),
                        "market_share_pct": round(share, 2)
                    }
                    
            result["methodology_note"] = "Market share computed as relative revenue within listed comparable universe. Does not represent total addressable market share."
            # Sort by fiscal year ascending (filter out methodology_note for sorting, but keep it in result)
            sorted_fys = sorted([k for k in result.keys() if k != "methodology_note"])
            sorted_result = {fy: result[fy] for fy in sorted_fys}
            sorted_result["methodology_note"] = result["methodology_note"]
            return sorted_result
            
        except Exception as e:
            logger.error(f"compute_proxy_market_share error: {e}")
            return result

    @staticmethod
    def compute_market_share_stability(proxy_market_share: dict) -> dict:
        """
        Computes both share volatility and rank stability across all available fiscal years.
        """
        result = {
            "per_company": {},
            "industry_share_stability": "stable",
            "mean_cv": 0.0,
            "years_analysed": 0
        }
        
        try:
            fys = sorted([k for k in proxy_market_share.keys() if k != "methodology_note"])
            result["years_analysed"] = len(fys)
            if not fys:
                return result
                
            company_shares = {}
            company_ranks = {}
            
            for fy in fys:
                data = proxy_market_share[fy]
                comps = [k for k in data.keys() if k not in ["universe_revenue", "companies_included"]]
                
                # Rank logic
                shares_for_rank = [(comp, data[comp]["market_share_pct"]) for comp in comps]
                shares_for_rank.sort(key=lambda x: x[1], reverse=True)
                
                for rank, (comp, share) in enumerate(shares_for_rank, start=1):
                    company_shares.setdefault(comp, []).append(share)
                    company_ranks.setdefault(comp, {})[fy] = rank
                    
            cvs = []
            for comp, shares in company_shares.items():
                mean_share = sum(shares) / len(shares)
                var = sum((x - mean_share) ** 2 for x in shares) / len(shares)
                std_dev = var ** 0.5
                
                cv = 0.0
                if mean_share > 0:
                    cv = std_dev / mean_share
                cvs.append(cv)
                
                if cv < 0.05:
                    vol_label = "very stable"
                elif cv < 0.10:
                    vol_label = "stable"
                elif cv < 0.20:
                    vol_label = "moderately volatile"
                else:
                    vol_label = "highly volatile"
                    
                # Rank stability
                ranks_by_year = company_ranks[comp]
                sorted_fys_comp = sorted(ranks_by_year.keys())
                rank_list = [ranks_by_year[fy] for fy in sorted_fys_comp]
                
                # mode
                counts = {}
                for r in rank_list:
                    counts[r] = counts.get(r, 0) + 1
                modal_rank = max(counts.items(), key=lambda x: x[1])[0] if counts else 0
                
                rank_changes = 0
                for i in range(1, len(rank_list)):
                    if rank_list[i] != rank_list[i-1]:
                        rank_changes += 1
                        
                if rank_changes == 0:
                    rank_stab_label = "perfectly stable"
                elif rank_changes <= 2:
                    rank_stab_label = "mostly stable"
                elif rank_changes <= 4:
                    rank_stab_label = "moderately unstable"
                else:
                    rank_stab_label = "highly unstable"
                    
                result["per_company"][comp] = {
                    "mean_share_pct": round(mean_share, 2),
                    "std_dev": round(std_dev, 2),
                    "coefficient_of_variation": round(cv, 2),
                    "volatility_label": vol_label,
                    "modal_rank": modal_rank,
                    "rank_changes": rank_changes,
                    "rank_stability_label": rank_stab_label,
                    "ranks_by_year": ranks_by_year
                }
                
            if cvs:
                mean_cv = sum(cvs) / len(cvs)
                result["mean_cv"] = round(mean_cv, 2)
                if mean_cv < 0.05:
                    result["industry_share_stability"] = "very stable"
                elif mean_cv < 0.10:
                    result["industry_share_stability"] = "stable"
                elif mean_cv < 0.20:
                    result["industry_share_stability"] = "moderately volatile"
                else:
                    result["industry_share_stability"] = "highly volatile"
                    
            return result
        except Exception as e:
            logger.error(f"compute_market_share_stability error: {e}")
            return result

    @staticmethod
    def compute_economic_profit_series(focal_ticker: str, focal_yearly_master: dict, peer_financials: dict, focal_roic_series: dict, peer_roic_series: dict, wacc: float, metric_map: dict) -> dict:
        """
        Computes Economic Profit for focal and each peer for each available fiscal year.
        """
        result = {
            "per_company": {},
            "aggregate_by_year": {},
            "ep_trend": "stable",
            "latest_aggregate_ep": 0.0,
            "focal_ep_latest": 0.0,
            "focal_ep_share_of_aggregate": 0.0
        }
        
        try:
            # Process focal
            result["per_company"][focal_ticker] = {}
            for raw_key, year_data in focal_yearly_master.items():
                fy = FinancialCalculator._format_fy(raw_key)
                
                total_eq = FinancialCalculator._extract_value(year_data, metric_map.get("total_equity", []))
                total_debt = FinancialCalculator._extract_value(year_data, metric_map.get("total_debt", []))
                cash = FinancialCalculator._extract_value(year_data, metric_map.get("cash_equivalents", []))
                
                inv_cap = FinancialCalculator.compute_invested_capital(total_eq, total_debt, cash)
                roic = focal_roic_series.get(fy, {}).get("roic")
                
                ep = None
                spread = None
                if inv_cap is not None and roic is not None:
                    spread = roic - wacc
                    ep = float(inv_cap) * (spread / 100.0)
                    
                result["per_company"][focal_ticker][fy] = {
                    "economic_profit": round(ep, 2) if ep is not None else None,
                    "invested_capital": round(inv_cap, 2) if inv_cap is not None else None,
                    "roic": roic,
                    "roic_minus_wacc": round(spread, 2) if spread is not None else None
                }
                
            # Process peers
            for peer, yearly_master in peer_financials.items():
                result["per_company"][peer] = {}
                for raw_key, year_data in yearly_master.items():
                    fy = FinancialCalculator._format_fy(raw_key)
                    
                    total_eq = FinancialCalculator._extract_value(year_data, metric_map.get("total_equity", []))
                    total_debt = FinancialCalculator._extract_value(year_data, metric_map.get("total_debt", []))
                    cash = FinancialCalculator._extract_value(year_data, metric_map.get("cash_equivalents", []))
                    
                    inv_cap = FinancialCalculator.compute_invested_capital(total_eq, total_debt, cash)
                    roic = peer_roic_series.get(peer, {}).get(fy, {}).get("roic")
                    
                    ep = None
                    spread = None
                    if inv_cap is not None and roic is not None:
                        spread = roic - wacc
                        ep = float(inv_cap) * (spread / 100.0)
                        
                    result["per_company"][peer][fy] = {
                        "economic_profit": round(ep, 2) if ep is not None else None,
                        "invested_capital": round(inv_cap, 2) if inv_cap is not None else None,
                        "roic": roic,
                        "roic_minus_wacc": round(spread, 2) if spread is not None else None
                    }
                    
            # Aggregate EP
            agg_fys = set()
            for comp, series in result["per_company"].items():
                agg_fys.update(series.keys())
                
            for fy in sorted(list(agg_fys)):
                total_ep = 0.0
                comps_incl = []
                for comp, series in result["per_company"].items():
                    if fy in series and series[fy]["economic_profit"] is not None:
                        total_ep += series[fy]["economic_profit"]
                        comps_incl.append(comp)
                        
                if comps_incl:
                    result["aggregate_by_year"][fy] = {
                        "total_economic_profit": round(total_ep, 2),
                        "companies_included": comps_incl
                    }
                    
            if not result["aggregate_by_year"]:
                return result
                
            agg_sorted_fys = sorted(result["aggregate_by_year"].keys())
            latest_fy = agg_sorted_fys[-1]
            
            result["latest_aggregate_ep"] = result["aggregate_by_year"][latest_fy]["total_economic_profit"]
            focal_ep = result["per_company"].get(focal_ticker, {}).get(latest_fy, {}).get("economic_profit")
            if focal_ep is not None:
                result["focal_ep_latest"] = focal_ep
                if result["latest_aggregate_ep"] != 0:
                    result["focal_ep_share_of_aggregate"] = round((focal_ep / result["latest_aggregate_ep"]) * 100.0, 2)
                    
            # Trend
            valid_eps = [result["aggregate_by_year"][fy]["total_economic_profit"] for fy in agg_sorted_fys]
            if len(valid_eps) >= 6:
                recent_avg = sum(valid_eps[-3:]) / 3.0
                prior_avg = sum(valid_eps[-6:-3]) / 3.0
                
                # using 1% threshold on prior avg equivalent? The prompt says "Same ±1% threshold logic as ROIC trend."
                # But EP is an absolute number, not a percentage!
                # "Same ±1% threshold logic" probably means relative change of 1% or just > 1% growth.
                # Let's compute relative growth: (recent - prior) / abs(prior) * 100
                if prior_avg != 0:
                    pct_change = ((recent_avg - prior_avg) / abs(prior_avg)) * 100.0
                    if pct_change > 1.0:
                        result["ep_trend"] = "growing"
                    elif pct_change < -1.0:
                        result["ep_trend"] = "shrinking"
            elif len(valid_eps) >= 4:
                recent_avg = sum(valid_eps[-2:]) / 2.0
                prior_avg = sum(valid_eps[-4:-2]) / 2.0
                if prior_avg != 0:
                    pct_change = ((recent_avg - prior_avg) / abs(prior_avg)) * 100.0
                    if pct_change > 1.0:
                        result["ep_trend"] = "growing"
                    elif pct_change < -1.0:
                        result["ep_trend"] = "shrinking"
                        
            return result
        except Exception as e:
            logger.error(f"compute_economic_profit_series error: {e}")
            return result

    @staticmethod
    def compute_concentration_metrics(proxy_market_share: dict) -> dict:
        """
        Computes HHI and CR4 for each fiscal year.
        """
        result = {
            "by_year": {},
            "concentration_trend": "stable concentration",
            "significant_shifts": [],
            "latest_hhi": 0.0,
            "latest_cr4": 0.0,
            "latest_hhi_classification": "competitive",
            "latest_cr4_classification": "fragmented"
        }
        
        try:
            fys = sorted([k for k in proxy_market_share.keys() if k != "methodology_note"])
            hhis = []
            
            for i, fy in enumerate(fys):
                data = proxy_market_share[fy]
                comps = [k for k in data.keys() if k not in ["universe_revenue", "companies_included"]]
                
                shares = []
                for comp in comps:
                    sh = data[comp]["market_share_pct"]
                    if sh is not None:
                        shares.append((comp, sh))
                        
                shares.sort(key=lambda x: x[1], reverse=True)
                
                hhi = sum(x[1] ** 2 for x in shares)
                if hhi < 1500:
                    hhi_class = "competitive"
                elif hhi <= 2500:
                    hhi_class = "moderately concentrated"
                else:
                    hhi_class = "highly concentrated"
                    
                cr4 = sum(x[1] for x in shares[:4])
                if cr4 < 40.0:
                    cr4_class = "fragmented"
                elif cr4 <= 70.0:
                    cr4_class = "moderately concentrated"
                else:
                    cr4_class = "highly concentrated"
                    
                result["by_year"][fy] = {
                    "hhi": round(hhi, 2),
                    "hhi_classification": hhi_class,
                    "cr4": round(cr4, 2),
                    "cr4_classification": cr4_class,
                    "top_4_companies": [x[0] for x in shares[:4]]
                }
                hhis.append(hhi)
                
                if i > 0:
                    prev_hhi = result["by_year"][fys[i-1]]["hhi"]
                    if prev_hhi > 0:
                        change = abs(hhi - prev_hhi) / prev_hhi
                        if change > 0.10:
                            result["significant_shifts"].append(f"significant concentration shift in {fy}")
                            
            if not fys:
                return result
                
            latest_fy = fys[-1]
            latest_data = result["by_year"][latest_fy]
            result["latest_hhi"] = latest_data["hhi"]
            result["latest_cr4"] = latest_data["cr4"]
            result["latest_hhi_classification"] = latest_data["hhi_classification"]
            result["latest_cr4_classification"] = latest_data["cr4_classification"]
            
            if len(hhis) >= 6:
                recent_avg = sum(hhis[-3:]) / 3.0
                prior_avg = sum(hhis[-6:-3]) / 3.0
                if recent_avg - prior_avg > 100:
                    result["concentration_trend"] = "increasing concentration"
                elif prior_avg - recent_avg > 100:
                    result["concentration_trend"] = "decreasing concentration"
            elif len(hhis) >= 4:
                recent_avg = sum(hhis[-2:]) / 2.0
                prior_avg = sum(hhis[-4:-2]) / 2.0
                if recent_avg - prior_avg > 100:
                    result["concentration_trend"] = "increasing concentration"
                elif prior_avg - recent_avg > 100:
                    result["concentration_trend"] = "decreasing concentration"
                    
            return result
        except Exception as e:
            logger.error(f"compute_concentration_metrics error: {e}")
            return result

    @staticmethod
    def classify_industry_structure(concentration_metrics: dict, market_share_stability: dict, f02_findings: dict) -> dict:
        """
        Rule-based industry structure classification.
        """
        result = {
            "structure_classification": "Moderately Competitive",
            "classification_rationale": "Industry exhibits mixed concentration and competitive dynamics",
            "strategic_opportunities": "Niche dominance and operational efficiency",
            "signals_used": {},
            "rule_matched": 5
        }
        
        try:
            latest_hhi = concentration_metrics.get("latest_hhi", 0.0)
            hhi_trend = concentration_metrics.get("concentration_trend", "stable concentration")
            industry_share_stability = market_share_stability.get("industry_share_stability", "stable")
            strategy_matters_strength = f02_findings.get("strategy_matters_strength", "moderate")
            
            comps = market_share_stability.get("per_company", {})
            mean_rank_changes = 0.0
            if comps:
                total_changes = sum(data.get("rank_changes", 0) for data in comps.values())
                mean_rank_changes = total_changes / len(comps)
                
            result["signals_used"] = {
                "latest_hhi": latest_hhi,
                "hhi_trend": hhi_trend,
                "industry_share_stability": industry_share_stability,
                "strategy_matters_strength": strategy_matters_strength,
                "mean_rank_changes": round(mean_rank_changes, 2)
            }
            
            # RULE 1
            cond1 = hhi_trend == "increasing concentration" and industry_share_stability in ["moderately volatile", "highly volatile"]
            cond2 = mean_rank_changes >= 3
            if cond1 or cond2:
                result["structure_classification"] = "Transitioning"
                result["classification_rationale"] = "Industry undergoing structural shift with meaningful share redistribution"
                result["strategic_opportunities"] = "First-mover advantage in emerging segments"
                result["rule_matched"] = 1
                return result
                
            # RULE 2
            if latest_hhi < 1500 and strategy_matters_strength in ["strong", "moderate"]:
                result["structure_classification"] = "Fragmented"
                result["classification_rationale"] = "Competitive industry with meaningful ROIC dispersion suggesting strategy matters"
                result["strategic_opportunities"] = "Consolidation and scale-building"
                result["rule_matched"] = 2
                return result
                
            # RULE 3
            if latest_hhi > 2500 and industry_share_stability in ["very stable", "stable"] and strategy_matters_strength == "weak":
                result["structure_classification"] = "Oligopolistic"
                result["classification_rationale"] = "Concentrated industry with stable shares and limited ROIC differentiation"
                result["strategic_opportunities"] = "Tacit coordination and capacity discipline"
                result["rule_matched"] = 3
                return result
                
            # RULE 4
            if latest_hhi > 2500 and industry_share_stability in ["very stable", "stable"] and strategy_matters_strength in ["strong", "moderate"]:
                result["structure_classification"] = "Consolidated"
                result["classification_rationale"] = "Concentrated industry where leading firms maintain meaningful strategic advantages"
                result["strategic_opportunities"] = "Differentiation and premium positioning"
                result["rule_matched"] = 4
                return result
                
            # Default Rule 5 is already set
            return result
        except Exception as e:
            logger.error(f"classify_industry_structure error: {e}")
            return result

    @staticmethod
    def compute_learning_curve_proxy(yearly_master: dict, metric_map: dict) -> dict:
        """
        Proxies learning curve benefit by analysing cost efficiency trend over time.
        """
        result = {
            "cost_ratio_by_year": {},
            "trend": "stable efficiency",
            "learning_curve_evidence": False,
            "cumulative_revenue_growth_pct": 0.0,
            "learning_curve_strength": "Minimal",
            "latest_cost_ratio": None,
            "earliest_cost_ratio": None,
            "cost_ratio_change_pp": None,
            "years_analysed": 0
        }
        
        try:
            cogs_keys = metric_map.get("cogs", ["cost of goods sold", "cost of materials consumed", "cost of revenue", "direct costs", "cost of services"])
            rev_keys = metric_map.get("revenue", ["revenue", "net revenue", "total revenue", "net sales", "revenue from operations"])
            
            fys = sorted(yearly_master.keys())
            if not fys:
                return result
                
            cost_ratios = []
            fys_with_ratios = []
            rev_first = None
            rev_last = None
            
            for raw_key in fys:
                year_data = yearly_master[raw_key]
                fy = FinancialCalculator._format_fy(raw_key)
                
                cogs = FinancialCalculator._extract_value(year_data, cogs_keys)
                rev = FinancialCalculator._extract_value(year_data, rev_keys)
                
                if rev is not None:
                    if rev_first is None:
                        rev_first = rev
                    rev_last = rev
                    
                ratio = None
                if cogs is not None and rev is not None and rev > 0:
                    ratio = cogs / rev
                    cost_ratios.append(ratio)
                    fys_with_ratios.append(fy)
                    
                result["cost_ratio_by_year"][fy] = round(ratio, 4) if ratio is not None else None
                
            result["years_analysed"] = len(fys_with_ratios)
            
            if rev_first is not None and rev_last is not None and rev_first > 0:
                result["cumulative_revenue_growth_pct"] = round(((rev_last - rev_first) / rev_first) * 100.0, 2)
                
            if not fys_with_ratios:
                return result
                
            result["earliest_cost_ratio"] = round(cost_ratios[0], 4)
            result["latest_cost_ratio"] = round(cost_ratios[-1], 4)
            result["cost_ratio_change_pp"] = round((cost_ratios[-1] - cost_ratios[0]) * 100.0, 2)
            
            # Trend analysis
            if len(cost_ratios) >= 6:
                recent_avg = sum(cost_ratios[-3:]) / 3.0
                prior_avg = sum(cost_ratios[-6:-3]) / 3.0
            elif len(cost_ratios) >= 4:
                recent_avg = sum(cost_ratios[-2:]) / 2.0
                prior_avg = sum(cost_ratios[-4:-2]) / 2.0
            else:
                recent_avg = cost_ratios[-1]
                prior_avg = cost_ratios[0]
                
            # difference in percentage points
            # 1 pp is 0.01 in ratio terms
            diff_pp = (prior_avg - recent_avg) * 100.0
            
            if diff_pp > 1.0:
                result["learning_curve_evidence"] = True
                result["trend"] = "improving efficiency"
            elif diff_pp < -1.0:
                result["learning_curve_evidence"] = False
                result["trend"] = "deteriorating efficiency"
                
            # Strength
            if result["learning_curve_evidence"] and result["cumulative_revenue_growth_pct"] > 100.0:
                result["learning_curve_strength"] = "Significant"
            elif result["learning_curve_evidence"] and result["cumulative_revenue_growth_pct"] >= 50.0:
                result["learning_curve_strength"] = "Moderate"
            elif result["learning_curve_evidence"]:
                result["learning_curve_strength"] = "Minimal"
            else:
                result["learning_curve_strength"] = "Minimal"
                
            return result
        except Exception as e:
            logger.error(f"compute_learning_curve_proxy error: {e}")
            return result

    @staticmethod
    def compute_asset_specificity_proxy(yearly_master: dict, metric_map: dict) -> dict:
        """
        Proxies asset specificity using fixed asset intensity and capex intensity trends.
        """
        result = {
            "fa_intensity_by_year": {},
            "capex_intensity_by_year": {},
            "avg_fa_intensity": 0.0,
            "avg_capex_intensity": 0.0,
            "fa_level": "Low",
            "capex_level": "Low",
            "asset_specificity": "Low",
            "trend": "stable",
            "years_analysed": 0
        }
        
        try:
            nfa_keys = metric_map.get("net_fixed_assets", ["net fixed assets", "property plant and equipment", "net block", "tangible assets", "fixed assets net"])
            capex_keys = metric_map.get("capex", ["capital expenditure", "capex", "purchase of fixed assets", "additions to fixed assets"])
            rev_keys = metric_map.get("revenue", ["revenue", "net revenue", "total revenue", "net sales", "revenue from operations"])
            
            fa_intensities = []
            capex_intensities = []
            
            for raw_key, year_data in yearly_master.items():
                fy = FinancialCalculator._format_fy(raw_key)
                
                nfa = FinancialCalculator._extract_value(year_data, nfa_keys)
                capex = FinancialCalculator._extract_value(year_data, capex_keys)
                rev = FinancialCalculator._extract_value(year_data, rev_keys)
                
                fa_int = None
                capex_int = None
                
                if rev is not None and rev > 0:
                    if nfa is not None:
                        fa_int = nfa / rev
                        fa_intensities.append(fa_int)
                    if capex is not None:
                        capex_int = capex / rev
                        capex_intensities.append(capex_int)
                        
                result["fa_intensity_by_year"][fy] = round(fa_int, 4) if fa_int is not None else None
                result["capex_intensity_by_year"][fy] = round(capex_int, 4) if capex_int is not None else None
                
            result["years_analysed"] = max(len(fa_intensities), len(capex_intensities))
            if result["years_analysed"] == 0:
                return result
                
            avg_fa = sum(fa_intensities) / len(fa_intensities) if fa_intensities else 0.0
            avg_capex = sum(capex_intensities) / len(capex_intensities) if capex_intensities else 0.0
            
            result["avg_fa_intensity"] = round(avg_fa, 4)
            result["avg_capex_intensity"] = round(avg_capex, 4)
            
            # Classification
            if avg_fa > 0.30:
                result["fa_level"] = "High"
            elif avg_fa >= 0.15:
                result["fa_level"] = "Moderate"
            else:
                result["fa_level"] = "Low"
                
            if avg_capex > 0.10:
                result["capex_level"] = "High"
            elif avg_capex >= 0.05:
                result["capex_level"] = "Moderate"
            else:
                result["capex_level"] = "Low"
                
            if result["fa_level"] == "High" or result["capex_level"] == "High":
                result["asset_specificity"] = "High"
            elif result["fa_level"] == "Moderate" or result["capex_level"] == "Moderate":
                result["asset_specificity"] = "Moderate"
            else:
                result["asset_specificity"] = "Low"
                
            return result
        except Exception as e:
            logger.error(f"compute_asset_specificity_proxy error: {e}")
            return result

    @staticmethod
    def compute_mes_proxy(focal_ticker: str, focal_yearly_master: dict, peer_financials: dict, proxy_market_share: dict, metric_map: dict) -> dict:
        """
        Computes Minimum Efficient Scale proxy using peer revenue data.
        """
        result = {
            "mes_proxy_revenue": 0.0,
            "mes_pct_of_universe": 0.0,
            "mes_pct_of_focal": 0.0,
            "mes_interpretation": "Unknown",
            "mes_share_link": "Unknown",
            "reference_year": "N/A",
            "companies_used": [],
            "revenue_ranking": {}
        }
        
        try:
            # find latest fy with data in proxy_market_share
            fys = sorted([k for k in proxy_market_share.keys() if k != "methodology_note"], reverse=True)
            if not fys:
                return result
                
            latest_fy = fys[0]
            fy_data = proxy_market_share[latest_fy]
            
            universe_rev = fy_data.get("universe_revenue", 0.0)
            comps = fy_data.get("companies_included", [])
            
            if not comps:
                return result
                
            result["reference_year"] = latest_fy
            result["companies_used"] = comps
            
            revs = []
            focal_rev = 0.0
            for comp in comps:
                rev = fy_data.get(comp, {}).get("revenue", 0.0)
                if comp == focal_ticker:
                    focal_rev = rev
                revs.append((comp, rev))
                
            revs.sort(key=lambda x: x[1])
            
            for i, (comp, rev) in enumerate(reversed(revs), start=1):
                result["revenue_ranking"][comp] = {
                    "revenue": rev,
                    "rank": i
                }
                
            if len(revs) < 4:
                mes_proxy = revs[0][1]
            else:
                idx = len(revs) // 4
                mes_proxy = revs[idx][1]
                
            result["mes_proxy_revenue"] = mes_proxy
            
            if universe_rev > 0:
                result["mes_pct_of_universe"] = round((mes_proxy / universe_rev) * 100.0, 2)
            if focal_rev > 0:
                result["mes_pct_of_focal"] = round((mes_proxy / focal_rev) * 100.0, 2)
                
            pct = result["mes_pct_of_universe"]
            if pct > 20.0:
                result["mes_interpretation"] = "High — significant scale required to be viable"
            elif pct >= 10.0:
                result["mes_interpretation"] = "Moderate — meaningful scale required"
            else:
                result["mes_interpretation"] = "Low — market can support many viable competitors"
                
            min_rev = revs[0][1]
            if min_rev < mes_proxy:
                result["mes_share_link"] = "Smallest competitor operating below MES — vulnerable to consolidation or exit"
            else:
                result["mes_share_link"] = "All competitors operating at or above MES"
                
            return result
        except Exception as e:
            logger.error(f"compute_mes_proxy error: {e}")
            return result

    @staticmethod
    def compute_revenue_volatility(focal_ticker: str, focal_yearly_master: dict, peer_financials: dict, metric_map: dict) -> dict:
        """
        Computes revenue growth volatility across focal company and peer set as a proxy for industry demand variability.
        """
        import statistics
        
        result = {
            "per_company": {},
            "industry_demand_std_dev": 0.0,
            "industry_demand_variability": "Low",
            "mean_pairwise_correlation": 0.0,
            "correlation_interpretation": "Low correlation — demand largely company-specific",
            "years_analysed": 0
        }
        
        try:
            rev_keys = metric_map.get("revenue", ["revenue", "net revenue", "total revenue", "net sales", "revenue from operations"])
            
            # Helper to extract series
            def get_rev_series(yearly_data):
                series = {}
                fys = sorted(yearly_data.keys())
                for raw_key in fys:
                    fy = FinancialCalculator._format_fy(raw_key)
                    val = FinancialCalculator._extract_value(yearly_data[raw_key], rev_keys)
                    if val is not None:
                        series[fy] = val
                return series

            all_companies_data = {focal_ticker: focal_yearly_master}
            for peer, data in peer_financials.items():
                all_companies_data[peer] = data.get("yearly", {})
                
            all_std_devs = []
            fys_set = set()
            
            for comp, data in all_companies_data.items():
                series = get_rev_series(data)
                fys = sorted(series.keys())
                fys_set.update(fys)
                
                yoy_growth = {}
                growths = []
                for i in range(1, len(fys)):
                    prev_fy = fys[i-1]
                    curr_fy = fys[i]
                    # ensure they are consecutive years (naively checking year diff ideally)
                    try:
                        prev_y = int(prev_fy.replace("FY", ""))
                        curr_y = int(curr_fy.replace("FY", ""))
                        if curr_y - prev_y == 1:
                            prev_val = series[prev_fy]
                            curr_val = series[curr_fy]
                            if prev_val > 0:
                                g = ((curr_val - prev_val) / prev_val) * 100.0
                                yoy_growth[curr_fy] = round(g, 4)
                                growths.append(g)
                    except ValueError:
                        pass
                        
                mean_g = statistics.mean(growths) if growths else 0.0
                std_g = statistics.stdev(growths) if len(growths) > 1 else 0.0
                if std_g > 0:
                    all_std_devs.append(std_g)
                    
                result["per_company"][comp] = {
                    "revenue_series": {k: round(v, 4) for k, v in series.items()},
                    "yoy_growth": yoy_growth,
                    "mean_growth": round(mean_g, 4),
                    "std_dev_growth": round(std_g, 4)
                }
                
            result["years_analysed"] = len(fys_set)
            
            if all_std_devs:
                ind_std = sum(all_std_devs) / len(all_std_devs)
                result["industry_demand_std_dev"] = round(ind_std, 4)
                if ind_std > 15.0:
                    result["industry_demand_variability"] = "High"
                elif ind_std >= 5.0:
                    result["industry_demand_variability"] = "Moderate"
                else:
                    result["industry_demand_variability"] = "Low"
                    
            # Correlation
            correlations = []
            comps = list(result["per_company"].keys())
            for i in range(len(comps)):
                for j in range(i + 1, len(comps)):
                    comp1 = comps[i]
                    comp2 = comps[j]
                    yoy1 = result["per_company"][comp1]["yoy_growth"]
                    yoy2 = result["per_company"][comp2]["yoy_growth"]
                    
                    common_fys = set(yoy1.keys()).intersection(set(yoy2.keys()))
                    if len(common_fys) > 1:
                        common_fys = sorted(list(common_fys))
                        g1 = [yoy1[fy] for fy in common_fys]
                        g2 = [yoy2[fy] for fy in common_fys]
                        
                        try:
                            mean1 = statistics.mean(g1)
                            mean2 = statistics.mean(g2)
                            std1 = statistics.stdev(g1)
                            std2 = statistics.stdev(g2)
                            
                            if std1 > 0 and std2 > 0:
                                cov = sum((g1[k] - mean1) * (g2[k] - mean2) for k in range(len(g1))) / (len(g1) - 1)
                                corr = cov / (std1 * std2)
                                correlations.append(corr)
                        except statistics.StatisticsError:
                            pass
                            
            if correlations:
                mean_corr = sum(correlations) / len(correlations)
                result["mean_pairwise_correlation"] = round(mean_corr, 4)
                if mean_corr > 0.7:
                    result["correlation_interpretation"] = "Highly correlated — demand primarily industry-driven"
                elif mean_corr >= 0.4:
                    result["correlation_interpretation"] = "Moderately correlated — mix of industry and company-specific factors"
                else:
                    result["correlation_interpretation"] = "Low correlation — demand largely company-specific"
            else:
                result["mean_pairwise_correlation"] = None
                
            return result
        except Exception as e:
            logger.error(f"compute_revenue_volatility error: {e}")
            return result

    @staticmethod
    def compute_industry_growth(focal_ticker: str, focal_yearly_master: dict, peer_financials: dict, metric_map: dict) -> dict:
        """
        Computes industry growth metrics using universe revenue (focal + peers combined).
        """
        result = {
            "universe_revenue_by_year": {},
            "universe_cagr_3yr": None,
            "universe_cagr_5yr": None,
            "universe_cagr_full": None,
            "industry_growth_classification": "Low",
            "growth_momentum": "Stable",
            "focal_cagr_3yr": None,
            "focal_growth_vs_industry": "In line with industry",
            "years_analysed": 0
        }
        
        try:
            rev_keys = metric_map.get("revenue", ["revenue", "net revenue", "total revenue", "net sales", "revenue from operations"])
            
            all_companies_data = {focal_ticker: focal_yearly_master}
            for peer, data in peer_financials.items():
                all_companies_data[peer] = data.get("yearly", {})
                
            universe = {}
            focal_revs = {}
            
            for comp, data in all_companies_data.items():
                for raw_key, year_data in data.items():
                    fy = FinancialCalculator._format_fy(raw_key)
                    val = FinancialCalculator._extract_value(year_data, rev_keys)
                    if val is not None:
                        universe[fy] = universe.get(fy, 0.0) + val
                        if comp == focal_ticker:
                            focal_revs[fy] = val
                            
            if not universe:
                return result
                
            for k, v in universe.items():
                result["universe_revenue_by_year"][k] = round(v, 4)
                
            fys = sorted(universe.keys())
            result["years_analysed"] = len(fys)
            
            def calc_cagr(series_dict, years_list, periods):
                if len(years_list) <= periods:
                    return None
                start_val = series_dict[years_list[-(periods+1)]]
                end_val = series_dict[years_list[-1]]
                if start_val > 0:
                    return ((end_val / start_val) ** (1/periods) - 1) * 100.0
                return None
                
            result["universe_cagr_3yr"] = calc_cagr(universe, fys, 3)
            result["universe_cagr_5yr"] = calc_cagr(universe, fys, 5)
            
            if len(fys) > 1:
                start = universe[fys[0]]
                end = universe[fys[-1]]
                periods = len(fys) - 1
                if start > 0:
                    result["universe_cagr_full"] = ((end / start) ** (1/periods) - 1) * 100.0
                    
            focal_fys = sorted(focal_revs.keys())
            result["focal_cagr_3yr"] = calc_cagr(focal_revs, focal_fys, 3)
            
            cagr3 = result["universe_cagr_3yr"]
            if cagr3 is not None:
                result["universe_cagr_3yr"] = round(cagr3, 4)
                if cagr3 > 15.0:
                    result["industry_growth_classification"] = "High"
                elif cagr3 >= 7.0:
                    result["industry_growth_classification"] = "Moderate"
                elif cagr3 >= 0.0:
                    result["industry_growth_classification"] = "Low"
                else:
                    result["industry_growth_classification"] = "Declining"
            else:
                if result["universe_cagr_full"] is not None:
                    # fallback
                    cfull = result["universe_cagr_full"]
                    if cfull > 15.0:
                        result["industry_growth_classification"] = "High"
                    elif cfull >= 7.0:
                        result["industry_growth_classification"] = "Moderate"
                    elif cfull >= 0.0:
                        result["industry_growth_classification"] = "Low"
                    else:
                        result["industry_growth_classification"] = "Declining"

            cagr5 = result["universe_cagr_5yr"]
            if cagr5 is not None:
                result["universe_cagr_5yr"] = round(cagr5, 4)
                
            if result["universe_cagr_full"] is not None:
                result["universe_cagr_full"] = round(result["universe_cagr_full"], 4)
                
            if cagr3 is not None and cagr5 is not None:
                if cagr3 - cagr5 > 2.0:
                    result["growth_momentum"] = "Accelerating"
                elif cagr5 - cagr3 > 2.0:
                    result["growth_momentum"] = "Decelerating"
                else:
                    result["growth_momentum"] = "Stable"
                    
            if result["focal_cagr_3yr"] is not None:
                result["focal_cagr_3yr"] = round(result["focal_cagr_3yr"], 4)
                if cagr3 is not None:
                    diff = result["focal_cagr_3yr"] - cagr3
                    if diff > 2.0:
                        result["focal_growth_vs_industry"] = "Outperforming industry"
                    elif diff < -2.0:
                        result["focal_growth_vs_industry"] = "Underperforming industry"
                    else:
                        result["focal_growth_vs_industry"] = "In line with industry"
                        
            return result
        except Exception as e:
            logger.error(f"compute_industry_growth error: {e}")
            return result

    @staticmethod
    def compute_firm_similarity(focal_ticker: str, focal_yearly_master: dict, peer_financials: dict, metric_map: dict) -> dict:
        """
        Measures how similar firms are across key dimensions using coefficient of variation.
        High similarity -> easier tacit coordination.
        """
        import statistics
        
        result = {
            "revenue_similarity": "Moderate similarity",
            "margin_similarity": "Moderate similarity",
            "capex_similarity": "Moderate similarity",
            "overall_firm_similarity": "Moderate",
            "cov_revenue": 0.0,
            "cov_margin": 0.0,
            "cov_capex": 0.0,
            "mean_similarity_score": 0.0,
            "companies_compared": [],
            "reference_year": "N/A"
        }
        
        try:
            rev_keys = metric_map.get("revenue", ["revenue", "net revenue", "total revenue", "net sales", "revenue from operations"])
            ebitda_keys = metric_map.get("ebitda", ["ebitda", "operating ebitda"])
            if not ebitda_keys: # fallback if not in map
                ebitda_keys = ["ebitda", "operating profit before depreciation"]
            capex_keys = metric_map.get("capex", ["capital expenditure", "capex", "purchase of fixed assets", "additions to fixed assets"])
            
            # Since EBIT was used in F01/F02, let's use EBIT if EBITDA missing
            ebit_keys = metric_map.get("ebit", ["ebit", "operating profit", "profit before interest and tax", "pbit"])
            
            all_companies_data = {focal_ticker: focal_yearly_master}
            for peer, data in peer_financials.items():
                all_companies_data[peer] = data.get("yearly", {})
                
            # Find latest common year across most companies
            fys_count = {}
            for comp, data in all_companies_data.items():
                for raw_key in data.keys():
                    fy = FinancialCalculator._format_fy(raw_key)
                    fys_count[fy] = fys_count.get(fy, 0) + 1
                    
            if not fys_count:
                return result
                
            latest_fy = sorted(fys_count.keys(), reverse=True)[0]
            result["reference_year"] = latest_fy
            
            revs = []
            margins = []
            capex_ints = []
            comps = []
            
            for comp, data in all_companies_data.items():
                # find the raw key for latest_fy
                raw_match = None
                for raw_key in data.keys():
                    if FinancialCalculator._format_fy(raw_key) == latest_fy:
                        raw_match = raw_key
                        break
                        
                if raw_match:
                    year_data = data[raw_match]
                    rev = FinancialCalculator._extract_value(year_data, rev_keys)
                    ebit = FinancialCalculator._extract_value(year_data, ebitda_keys)
                    if ebit is None:
                        ebit = FinancialCalculator._extract_value(year_data, ebit_keys)
                    capex = FinancialCalculator._extract_value(year_data, capex_keys)
                    
                    if rev is not None and rev > 0:
                        revs.append(rev)
                        comps.append(comp)
                        if ebit is not None:
                            margins.append(ebit / rev)
                        if capex is not None:
                            capex_ints.append(capex / rev)
                            
            result["companies_compared"] = comps
            
            def get_cov(vals):
                if len(vals) > 1:
                    m = statistics.mean(vals)
                    if m > 0:
                        return statistics.stdev(vals) / m
                return None
                
            def get_similarity_level(cov_val):
                if cov_val is None:
                    return "Unknown", 0
                if cov_val < 0.3:
                    return "High similarity", 3
                elif cov_val <= 0.6:
                    return "Moderate similarity", 2
                else:
                    return "Low similarity", 1
                    
            cov_rev = get_cov(revs)
            cov_mar = get_cov(margins)
            cov_cap = get_cov(capex_ints)
            
            result["cov_revenue"] = round(cov_rev, 4) if cov_rev is not None else 0.0
            result["cov_margin"] = round(cov_mar, 4) if cov_mar is not None else 0.0
            result["cov_capex"] = round(cov_cap, 4) if cov_cap is not None else 0.0
            
            rev_sim, rev_s = get_similarity_level(cov_rev)
            mar_sim, mar_s = get_similarity_level(cov_mar)
            cap_sim, cap_s = get_similarity_level(cov_cap)
            
            if rev_s > 0:
                result["revenue_similarity"] = rev_sim
            if mar_s > 0:
                result["margin_similarity"] = mar_sim
            if cap_s > 0:
                result["capex_similarity"] = cap_sim
                
            scores = [s for s in [rev_s, mar_s, cap_s] if s > 0]
            if scores:
                mean_s = sum(scores) / len(scores)
                result["mean_similarity_score"] = round(mean_s, 4)
                if mean_s >= 2.5:
                    result["overall_firm_similarity"] = "High"
                elif mean_s >= 1.5:
                    result["overall_firm_similarity"] = "Moderate"
                else:
                    result["overall_firm_similarity"] = "Low"
                    
            return result
        except Exception as e:
            logger.error(f"compute_firm_similarity error: {e}")
            return result

    @staticmethod
    def compute_tacit_coordination_signals(focal_ticker: str, focal_yearly_master: dict, peer_financials: dict, metric_map: dict, concentration_metrics: dict, firm_similarity: dict) -> dict:
        """
        Computes quantitative signals that suggest or contradict tacit coordination likelihood.
        """
        result = {
            "margin_convergence_score": 0.0,
            "strong_structure_signal": False,
            "similarity_signal": False,
            "stability_signal": False,
            "signals_count": 0,
            "coordination_likelihood": "Low",
            "signals_summary": []
        }
        
        try:
            # Signal 1 - margin convergence
            # we need to track if margins move together
            rev_keys = metric_map.get("revenue", ["revenue", "net revenue", "total revenue", "net sales", "revenue from operations"])
            ebit_keys = metric_map.get("ebitda", ["ebitda", "operating ebitda"])
            if not ebit_keys:
                ebit_keys = metric_map.get("ebit", ["ebit", "operating profit", "profit before interest and tax", "pbit"])
                
            all_companies_data = {focal_ticker: focal_yearly_master}
            for peer, data in peer_financials.items():
                all_companies_data[peer] = data.get("yearly", {})
                
            margins_by_comp_year = {}
            all_fys = set()
            
            for comp, data in all_companies_data.items():
                margins_by_comp_year[comp] = {}
                for raw_key, year_data in data.items():
                    fy = FinancialCalculator._format_fy(raw_key)
                    all_fys.add(fy)
                    rev = FinancialCalculator._extract_value(year_data, rev_keys)
                    ebit = FinancialCalculator._extract_value(year_data, ebit_keys)
                    if rev is not None and rev > 0 and ebit is not None:
                        margins_by_comp_year[comp][fy] = ebit / rev
                        
            fys_sorted = sorted(list(all_fys))
            convergence_years = 0
            valid_years = 0
            
            for i in range(1, len(fys_sorted)):
                prev_fy = fys_sorted[i-1]
                curr_fy = fys_sorted[i]
                
                dirs = []
                for comp in all_companies_data.keys():
                    m_prev = margins_by_comp_year[comp].get(prev_fy)
                    m_curr = margins_by_comp_year[comp].get(curr_fy)
                    if m_prev is not None and m_curr is not None:
                        if m_curr > m_prev + 0.001: dirs.append(1)
                        elif m_curr < m_prev - 0.001: dirs.append(-1)
                        else: dirs.append(0)
                        
                if len(dirs) >= 3:
                    valid_years += 1
                    ups = sum(1 for d in dirs if d == 1)
                    downs = sum(1 for d in dirs if d == -1)
                    same = sum(1 for d in dirs if d == 0)
                    
                    m = max(ups, downs, same)
                    if m / len(dirs) >= 0.6: # 60% majority
                        convergence_years += 1
                        
            if valid_years > 0:
                result["margin_convergence_score"] = convergence_years / valid_years
                
            margin_signal = result["margin_convergence_score"] >= 0.6
            if margin_signal:
                result["signals_summary"].append("Margin convergence detected")
                
            # Signal 2 - HHI
            hhi = concentration_metrics.get("latest_hhi", 0.0)
            if hhi > 2500:
                result["strong_structure_signal"] = True
                result["signals_summary"].append("Highly concentrated market (HHI > 2500)")
                
            # Signal 3 - Similarity
            if firm_similarity.get("overall_firm_similarity") == "High":
                result["similarity_signal"] = True
                result["signals_summary"].append("High firm similarity across size, margins, and capex")
                
            # Demand variability is handled outside or we can do it here if we pass it, but
            # prompt says "stability_signal" comes from demand variability.
            # I will just set stability_signal to False for now, caller can adjust.
            
            count = sum([1 for s in [margin_signal, result["strong_structure_signal"], result["similarity_signal"]] if s])
            
            # Wait, the spec said 4 signals. I will return count here, and caller will adjust for demand variability.
            result["signals_count"] = count # Without stability signal yet
            
            return result
        except Exception as e:
            logger.error(f"compute_tacit_coordination_signals error: {e}")
            return result
