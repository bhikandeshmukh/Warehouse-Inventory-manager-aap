import pandas as pd
import numpy as np
from pathlib import Path
import threading
import os
import math
from datetime import datetime
import queue
import re

filedialog = None
messagebox = None

# SHEETS CREATED:
# - Summary (Overall Analysis & Insights)
# - SKU Detailed Analysis (Status-wise Sales & Returns)
# - Monthly SKU Analysis (Month-wise SKU Performance)
# - Monthly Summary (Month-by-month Breakdown)
# - All Brands (Combined Analysis)


class SalesReturnAnalyzer:
    def __init__(self, root=None):
        self.root = root
        self.order_file_path = None
        self.return_file_path = None
        self.output_folder = None
        self.order_df = None
        self.return_df = None
        self.files_valid = False
        self.analysis_running = False
        self.data_warnings = []
        self.ui_queue = queue.Queue()
        self.ui_queue_polling = False
        self.category_sheet_created = False

    def run_on_main_thread(self, callback):
        callback()

    def ensure_ui_queue_processing(self):
        return

    def process_ui_queue(self):
        return

    def set_progress_text(self, text):
        self.run_on_main_thread(lambda: self.progress_var.set(text))

    def set_progress_running(self, is_running):
        action = self.progress_bar.start if is_running else self.progress_bar.stop
        self.run_on_main_thread(action)

    def set_results_text_threadsafe(self, text):
        self.run_on_main_thread(lambda: self.update_results_text(text))

    def set_controls_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for widget_name in [
            "load_button",
            "clear_button",
            "order_template_button",
            "return_template_button",
            "theme_button",
        ]:
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.config(state=state)

        if getattr(self, "analyze_button", None) is not None:
            analyze_state = "normal" if enabled and self.files_valid else "disabled"
            self.analyze_button.config(state=analyze_state)

    def format_month_display(self, month_str):
        """Convert normalized month values to display format."""
        parsed = self.parse_month_value(month_str)
        return parsed.strftime("%b-%Y").upper() if parsed else str(month_str)

    def parse_month_value(self, month_value):
        if pd.isna(month_value):
            return None

        text = str(month_value).strip()
        if not text:
            return None

        for fmt in ("%Y-%m", "%b-%y", "%b-%Y", "%b %Y", "%b %y", "%Y/%m", "%m/%Y", "%m-%Y"):
            try:
                return datetime.strptime(text, fmt).replace(day=1)
            except ValueError:
                continue

        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.to_pydatetime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def normalize_month_value(self, month_value):
        parsed = self.parse_month_value(month_value)
        return parsed.strftime("%Y-%m") if parsed else np.nan

    def normalize_month_column(self, series):
        return series.apply(self.normalize_month_value)

    def sort_months_chronologically(self, months):
        month_dates = []
        for month in months:
            month_dates.append((self.parse_month_value(month) or datetime.max, month))
        month_dates.sort(key=lambda item: item[0])
        return [month for _, month in month_dates]

    def clean_column_names(self, dataframe):
        """Normalize incoming column labels so template variants map consistently."""
        cleaned = dataframe.copy()
        cleaned.columns = [
            re.sub(r"_+", "_", re.sub(r"[^0-9a-zA-Z]+", "_", str(column).strip().lower())).strip("_")
            for column in cleaned.columns
        ]
        return cleaned

    def normalize_status_value(self, value):
        if pd.isna(value):
            return ""
        return re.sub(r"\s+", " ", str(value).strip()).upper()

    def is_cancelled_status(self, value):
        return "CANCEL" in self.normalize_status_value(value)

    def is_return_status(self, value):
        normalized = self.normalize_status_value(value)
        return any(token in normalized for token in ("RETURN", "EXCHANGE", "RTO"))

    def prepare_single_file_data(self, raw_df):
        """
        Build sales and return dataframes from one combined template.

        The same input file contains sold, returned, exchanged, and cancelled rows.
        """
        combined_df = self.clean_column_names(raw_df)

        self.order_df = combined_df.copy()
        self.return_df = combined_df.copy()
        self.map_column_names()

        combined_df = self.order_df.copy()

        if "order_status" in combined_df.columns:
            combined_df["order_status"] = combined_df["order_status"].apply(self.normalize_status_value)
        else:
            combined_df["order_status"] = ""

        if "qty" in combined_df.columns:
            combined_df["qty"] = pd.to_numeric(combined_df["qty"], errors="coerce").fillna(0)

        if "month" in combined_df.columns:
            combined_df["month"] = self.normalize_month_column(combined_df["month"])

        if "selling_price" in combined_df.columns:
            combined_df["selling_price"] = pd.to_numeric(combined_df["selling_price"], errors="coerce")

        if "cost_price" in combined_df.columns:
            combined_df["cost_price"] = pd.to_numeric(combined_df["cost_price"], errors="coerce")

        if "return_exchange_reason" in combined_df.columns:
            reason_source = combined_df["return_exchange_reason"]
        elif "return_reason" in combined_df.columns:
            reason_source = combined_df["return_reason"]
        else:
            reason_source = ""

        if isinstance(reason_source, pd.Series):
            combined_df["return_reason"] = reason_source.fillna("").astype(str).str.strip()
        else:
            combined_df["return_reason"] = ""

        cancelled_mask = combined_df["order_status"].apply(self.is_cancelled_status)
        analysis_df = combined_df[~cancelled_mask].copy()

        self.order_df = analysis_df.copy()

        return_mask = analysis_df["order_status"].apply(self.is_return_status)
        self.return_df = analysis_df[return_mask].copy()
        self.return_df["quantity"] = self.return_df["qty"]
        reason_series = self.return_df["return_reason"].astype("string").str.strip()
        reason_series = reason_series.mask(reason_series.eq(""), pd.NA)
        self.return_df["return_reason"] = reason_series.fillna(self.return_df["order_status"]).fillna("Unknown / Missing")

        return {
            "input_rows": len(combined_df),
            "sales_rows": len(self.order_df),
            "return_rows": len(self.return_df),
            "cancelled_rows": int(cancelled_mask.sum()),
        }

    def make_safe_sheet_name(self, value, existing_names=None, suffix=""):
        invalid_chars = r'[]:*?/\\'
        base_name = "".join("_" if char in invalid_chars else char for char in str(value or "Sheet"))
        base_name = base_name.strip() or "Sheet"
        max_base_length = max(1, 31 - len(suffix))
        base_name = base_name[:max_base_length].rstrip() or "Sheet"
        candidate = f"{base_name}{suffix}"

        if existing_names is None:
            return candidate[:31]

        if candidate not in existing_names:
            existing_names.add(candidate)
            return candidate

        counter = 2
        while True:
            counter_suffix = f" {counter}"
            trimmed_base = base_name[: max(1, 31 - len(suffix) - len(counter_suffix))].rstrip() or "Sheet"
            candidate = f"{trimmed_base}{counter_suffix}{suffix}"
            if candidate not in existing_names:
                existing_names.add(candidate)
                return candidate
            counter += 1

    def map_column_names(self):
        """Map common column name variations to expected names"""
        # Order sheet column mappings
        order_mappings = {
            # Brand variations
            "brand_name": "brand",
            "brandname": "brand",
            "brand_id": "brand",
            "manufacturer": "brand",
            "company": "brand",
            # SKU variations
            "sku": "my_sku",
            "product_sku": "my_sku",
            "item_sku": "my_sku",
            "product_id": "my_sku",
            "item_id": "my_sku",
            "product_code": "my_sku",
            "item_code": "my_sku",
            "seller_sku_code": "seller_sku_code",
            # Category variations
            "catagory": "category",
            "product_category": "category",
            "item_category": "category",
            # Quantity variations
            "quantity": "qty",
            "quantity_sold": "qty",
            "units_sold": "qty",
            "sale_qty": "qty",
            "sales_qty": "qty",
            "order_qty": "qty",
            "order_quantity": "qty",
            # Status variations
            "status": "order_status",
            "order_state": "order_status",
            "delivery_status": "order_status",
            "return_exchange_reason": "return_reason",
            # Month variations
            "order_month": "month",
            "sale_month": "month",
            "transaction_month": "month",
            "period": "month",
            # Price variations
            "sale_price": "selling_price",
            "sellingprice": "selling_price",
            "cost": "cost_price",
            "costprice": "cost_price",
        }

        # Return sheet column mappings
        return_mappings = {
            # Brand variations (same as order)
            "brand_name": "brand",
            "brandname": "brand",
            "brand_id": "brand",
            "manufacturer": "brand",
            "company": "brand",
            # SKU variations (same as order)
            "sku": "my_sku",
            "product_sku": "my_sku",
            "item_sku": "my_sku",
            "product_id": "my_sku",
            "item_id": "my_sku",
            "product_code": "my_sku",
            "item_code": "my_sku",
            # Quantity variations
            "qty": "quantity",
            "return_qty": "quantity",
            "returned_qty": "quantity",
            "units_returned": "quantity",
            "return_units": "quantity",
            # Category variations
            "catagory": "category",
            "product_category": "category",
            "item_category": "category",
            # Return reason variations
            "reason": "return_reason",
            "return_type": "return_reason",
            "reason_for_return": "return_reason",
            "return_category": "return_reason",
            "return_exchange_reason": "return_reason",
            # Status variations
            "status": "order_status",
            "order_state": "order_status",
            "original_status": "order_status",
            # Month variations
            "return_month": "month",
            "transaction_month": "month",
            "period": "month",
        }

        # Apply mappings to order dataframe
        if self.order_df is not None:
            for old_name, new_name in order_mappings.items():
                if (
                    old_name in self.order_df.columns
                    and new_name not in self.order_df.columns
                ):
                    self.order_df = self.order_df.rename(columns={old_name: new_name})

        # Apply mappings to return dataframe
        if self.return_df is not None:
            for old_name, new_name in return_mappings.items():
                if (
                    old_name in self.return_df.columns
                    and new_name not in self.return_df.columns
                ):
                    self.return_df = self.return_df.rename(columns={old_name: new_name})

    def validate_required_columns(self):
        """Validate that required columns exist and show helpful messages"""
        required_order_cols = ["brand", "my_sku", "qty"]
        required_return_cols = ["brand", "my_sku", "quantity", "return_reason"]

        missing_order = [
            col for col in required_order_cols if col not in self.order_df.columns
        ]
        missing_return = [
            col for col in required_return_cols if col not in self.return_df.columns
        ]

        is_valid = not (missing_order or missing_return)

        if missing_order or missing_return:
            warning_msg = "COLUMN MAPPING WARNINGS:\n\n"

            if missing_order:
                warning_msg += f"INPUT TEMPLATE - Missing sales columns: {', '.join(missing_order)}\n"
                warning_msg += (
                    f"Available columns: {', '.join(self.order_df.columns)}\n\n"
                )

            if missing_return:
                warning_msg += f"INPUT TEMPLATE - Missing return columns: {', '.join(missing_return)}\n"
                warning_msg += (
                    f"Available columns: {', '.join(self.return_df.columns)}\n\n"
                )

            warning_msg += "SOLUTION:\n"
            warning_msg += "1. Use the single input template CSV structure, OR\n"
            warning_msg += "2. Rename your columns to match the required names:\n\n"
            warning_msg += "INPUT TEMPLATE REQUIRED COLUMNS:\n"
            warning_msg += "- brand (product brand)\n"
            warning_msg += "- my_sku (unique product identifier)\n"
            warning_msg += "- qty (quantity sold)\n"
            warning_msg += "- order_status (DELIVERED / RETURN / EXCHANGE / CANCELLED)\n"
            warning_msg += "- RETURN/EXCHANGE REASON (preferred reason column)\n"
            warning_msg += "- return_reason (legacy alias, also supported)\n"
            warning_msg += "- month (optional: YYYY-MM or Apr-25 style)"

            messagebox.showwarning("Column Mapping Warning", warning_msg)

        return is_valid

    def setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # Title with modern styling
        title_label = ttk.Label(
            main_frame, text="📊 Sales & Return Analysis Tool", style="Title.TLabel"
        )
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        # File selection section with modern styling
        file_frame = ttk.LabelFrame(main_frame, text="📁 File Selection", padding="15")
        file_frame.grid(
            row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 20)
        )
        file_frame.columnconfigure(1, weight=1)

        # Order sheet selection
        ttk.Label(file_frame, text="Order Sheet (CSV):").grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        ttk.Entry(file_frame, textvariable=self.order_file_path, width=50).grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=(10, 5), pady=5
        )
        ttk.Button(file_frame, text="Browse", command=self.browse_order_file).grid(
            row=0, column=2, pady=5
        )

        # Return sheet selection
        ttk.Label(file_frame, text="Return Sheet (CSV):").grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        ttk.Entry(file_frame, textvariable=self.return_file_path, width=50).grid(
            row=1, column=1, sticky=(tk.W, tk.E), padx=(10, 5), pady=5
        )
        ttk.Button(file_frame, text="Browse", command=self.browse_return_file).grid(
            row=1, column=2, pady=5
        )

        # Output folder selection
        ttk.Label(file_frame, text="Output Folder:").grid(
            row=2, column=0, sticky=tk.W, pady=5
        )
        ttk.Entry(file_frame, textvariable=self.output_folder, width=50).grid(
            row=2, column=1, sticky=(tk.W, tk.E), padx=(10, 5), pady=5
        )
        ttk.Button(file_frame, text="Browse", command=self.browse_output_folder).grid(
            row=2, column=2, pady=5
        )

        # File info section with modern styling
        info_frame = ttk.LabelFrame(main_frame, text="ℹ️ File Information", padding="15")
        info_frame.grid(
            row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 20)
        )
        info_frame.columnconfigure(0, weight=1)

        self.info_text = tk.Text(
            info_frame,
            height=8,
            width=80,
            state=tk.DISABLED,
            wrap=tk.WORD,
            bg="white",
            font=("Consolas", 9),
        )
        scrollbar = ttk.Scrollbar(
            info_frame, orient=tk.VERTICAL, command=self.info_text.yview
        )
        self.info_text.configure(yscrollcommand=scrollbar.set)

        self.info_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        info_frame.rowconfigure(0, weight=1)

        # Template generation section with modern styling
        template_frame = ttk.LabelFrame(
            main_frame, text="📋 Template Generation", padding="15"
        )
        template_frame.grid(
            row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 20)
        )

        template_button_frame = ttk.Frame(template_frame)
        template_button_frame.pack()

        self.order_template_button = ttk.Button(
            template_button_frame,
            text="Generate Order Sheet Template",
            command=self.generate_order_template,
        )
        self.order_template_button.pack(side=tk.LEFT, padx=(0, 10))

        self.return_template_button = ttk.Button(
            template_button_frame,
            text="Generate Return Sheet Template",
            command=self.generate_return_template,
        )
        self.return_template_button.pack(side=tk.LEFT)

        # Control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=(0, 20))

        self.load_button = ttk.Button(
            button_frame,
            text="📂 Load & Preview Files",
            command=self.load_files,
            style="Accent.TButton",
        )
        self.load_button.pack(side=tk.LEFT, padx=(0, 10))

        self.analyze_button = ttk.Button(
            button_frame,
            text="🔍 Generate Analysis",
            command=self.start_analysis,
            state=tk.DISABLED,
        )
        self.analyze_button.pack(side=tk.LEFT, padx=(0, 10))

        self.clear_button = ttk.Button(
            button_frame, text="🗑️ Clear All", command=self.clear_all
        )
        self.clear_button.pack(side=tk.LEFT, padx=(0, 10))

        # Theme selector (only if ttkthemes is available)
        if TTKTHEMES_AVAILABLE:
            self.theme_button = ttk.Button(
                button_frame, text="🎨 Change Theme", command=self.show_theme_selector
            )
            self.theme_button.pack(side=tk.LEFT)

        # Progress section with modern styling
        progress_frame = ttk.LabelFrame(main_frame, text="⏳ Progress", padding="15")
        progress_frame.grid(
            row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 20)
        )
        progress_frame.columnconfigure(0, weight=1)

        self.progress_var = tk.StringVar(value="Ready to start...")
        self.progress_label = ttk.Label(progress_frame, textvariable=self.progress_var)
        self.progress_label.grid(row=0, column=0, sticky=tk.W)

        self.progress_bar = ttk.Progressbar(progress_frame, mode="indeterminate")
        self.progress_bar.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(5, 0))

        # Results section with modern styling
        results_frame = ttk.LabelFrame(
            main_frame, text="📈 Analysis Results", padding="15"
        )
        results_frame.grid(
            row=6, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 20)
        )
        results_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(6, weight=1)

        self.results_text = tk.Text(
            results_frame,
            height=10,
            width=80,
            state=tk.DISABLED,
            wrap=tk.WORD,
            bg="white",
            font=("Consolas", 9),
        )
        results_scrollbar = ttk.Scrollbar(
            results_frame, orient=tk.VERTICAL, command=self.results_text.yview
        )
        self.results_text.configure(yscrollcommand=results_scrollbar.set)

        self.results_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        results_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        results_frame.rowconfigure(0, weight=1)

        # Configure styles
        self.setup_styles()

    def setup_styles(self):
        if TTKTHEMES_AVAILABLE:
            # Use ThemedStyle for better theme support
            style = ThemedStyle(self.root)

            # Configure custom styles with theme support
            style.configure(
                "Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#2c3e50"
            )

            style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

            style.configure("Info.TLabel", font=("Segoe UI", 9), foreground="#34495e")

            # Configure frame styles for better appearance
            style.configure("TLabelFrame", relief="flat", borderwidth=1)

        else:
            # Fallback to standard ttk.Style
            style = ttk.Style()
            style.configure("Title.TLabel", font=("Arial", 16, "bold"))
            style.configure("Accent.TButton", foreground="white")

    def browse_order_file(self):
        filename = filedialog.askopenfilename(
            title="Select Input CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if filename:
            self.order_file_path.set(filename)

    def browse_return_file(self):
        filename = filedialog.askopenfilename(
            title="Select Return Sheet CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if filename:
            self.return_file_path.set(filename)

    def browse_output_folder(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_folder.set(folder)

    def update_info_text(self, text):
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(tk.END, text)
        self.info_text.config(state=tk.DISABLED)

    def update_results_text(self, text):
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(tk.END, text)
        self.results_text.config(state=tk.DISABLED)

    def load_files(self):
        if not self.order_file_path.get():
            messagebox.showerror("Error", "Please select the input CSV file.")
            return

        try:
            self.set_progress_text("Loading files...")
            self.set_progress_running(True)

            input_path = Path(self.order_file_path.get())
            raw_df = pd.read_csv(input_path)

            self.set_progress_text("Preparing combined sales and return data...")
            stats = self.prepare_single_file_data(raw_df)
            self.files_valid = self.validate_required_columns()

            raw_columns = ", ".join(self.clean_column_names(raw_df).columns)
            info_text = f"""INPUT FILE INFORMATION:
File: {input_path.name}
Rows: {stats['input_rows']:,}
Columns: {len(raw_df.columns)}
Normalized Columns: {raw_columns}

Sample Data (First 3 rows):
{raw_df.head(3).to_string()}

DERIVED SALES DATA:
Rows Included: {stats['sales_rows']:,}
Unique Brands: {self.order_df['brand'].nunique() if 'brand' in self.order_df.columns else 'MISSING BRAND COLUMN'}
Unique SKUs: {self.order_df['my_sku'].nunique() if 'my_sku' in self.order_df.columns else 'MISSING MY_SKU COLUMN'}
Total Quantity: {self.order_df['qty'].sum() if 'qty' in self.order_df.columns else 'MISSING QTY COLUMN'}

DERIVED RETURN DATA:
Rows Included: {stats['return_rows']:,}
Unique Brands: {self.return_df['brand'].nunique() if 'brand' in self.return_df.columns else 'MISSING BRAND COLUMN'}
Unique SKUs: {self.return_df['my_sku'].nunique() if 'my_sku' in self.return_df.columns else 'MISSING MY_SKU COLUMN'}
Total Return Quantity: {self.return_df['quantity'].sum() if 'quantity' in self.return_df.columns else 'MISSING QUANTITY COLUMN'}

FILTERS APPLIED:
Cancelled Rows Ignored: {stats['cancelled_rows']:,}
Return Rows Derived From Status: RETURN / EXCHANGE / RTO

Files loaded successfully. You can now generate the analysis."""

            if "return_reason" in self.return_df.columns and not self.return_df.empty:
                top_return_reasons = ", ".join(self.return_df["return_reason"].value_counts().head(5).index)
                info_text += f"\n\nTop Return Reasons: {top_return_reasons}"

            self.update_info_text(info_text)
            self.analyze_button.config(state="normal" if self.files_valid else "disabled")
            self.set_progress_text(
                "File loaded successfully!" if self.files_valid else "File loaded with column warnings."
            )

        except Exception as e:
            self.files_valid = False
            messagebox.showerror("Error", f"Failed to load files:\n{str(e)}")
            self.set_progress_text("Error loading files")
        finally:
            self.set_progress_running(False)

    def start_analysis(self):
        if self.order_df is None or self.return_df is None or not self.files_valid:
            messagebox.showerror("Error", "Please load files first.")
            return

        if self.analysis_running:
            messagebox.showwarning("Analysis Running", "An analysis run is already in progress.")
            return

        self.analysis_running = True
        self.set_controls_enabled(False)

        # Run analysis in separate thread to prevent GUI freezing
        thread = threading.Thread(target=self.run_analysis)
        thread.daemon = True
        thread.start()

    def run_analysis(self):
        try:
            self.set_progress_running(True)
            self.set_progress_text("Starting analysis...")
            self.category_sheet_created = False

            # The main analysis code from your script
            self.set_progress_text("Preparing sales summary...")

            # Prepare sales summary from ORDERSHEET
            sales_summary = (
                self.order_df.groupby(["brand", "my_sku"])["qty"].sum().reset_index()
            )
            sales_summary = sales_summary.rename(columns={"qty": "sale_unit"})

            # Create all brands sales summary
            all_brands_sales = (
                sales_summary.groupby("my_sku")["sale_unit"].sum().reset_index()
            )

            self.set_progress_text("Creating pivot tables...")

            # Create ALL BRANDS return pivot table (without month)
            pivot_all_brands = self.return_df.pivot_table(
                index="my_sku",
                columns="return_reason",
                values="quantity",
                aggfunc="sum",
                fill_value=0,
            )

            # Create ALL BRANDS return pivot table WITH MONTH
            if "month" in self.return_df.columns:
                pivot_all_brands_monthly = self.return_df.pivot_table(
                    index=["month", "my_sku"],
                    columns="return_reason",
                    values="quantity",
                    aggfunc="sum",
                    fill_value=0,
                )
            else:
                # If no month column, create empty dataframe with same structure
                pivot_all_brands_monthly = pd.DataFrame()

            # Create BRAND-WISE pivot tables (without month)
            brandwise_pivots = {}
            for brand, group in self.return_df.groupby("brand"):
                pivot = group.pivot_table(
                    index="my_sku",
                    columns="return_reason",
                    values="quantity",
                    aggfunc="sum",
                    fill_value=0,
                )
                brandwise_pivots[brand] = pivot

            # Create BRAND-WISE pivot tables WITH MONTH
            brandwise_pivots_monthly = {}
            if "month" in self.return_df.columns:
                for brand, group in self.return_df.groupby("brand"):
                    pivot = group.pivot_table(
                        index=["month", "my_sku"],
                        columns="return_reason",
                        values="quantity",
                        aggfunc="sum",
                        fill_value=0,
                    )
                    brandwise_pivots_monthly[brand] = pivot

            self.set_progress_text("Adding calculations...")

            # Helper function for regular pivot tables (without month)
            def add_sales_and_totals(pivot, sales_data):
                pivot = pivot.copy()
                pivot["RETURN TOTAL"] = pivot.sum(axis=1)
                pivot.reset_index(inplace=True)
                pivot.rename(columns={"my_sku": "MY SKU"}, inplace=True)

                sales_merge = sales_data[["my_sku", "sale_unit"]].copy()
                merged = pd.merge(
                    sales_merge, pivot, left_on="my_sku", right_on="MY SKU", how="outer"
                )

                if "my_sku" in merged.columns:
                    merged["MY SKU"] = merged["MY SKU"].fillna(merged["my_sku"])
                    merged.drop(columns=["my_sku"], inplace=True)
                if "brand" in merged.columns:
                    merged.drop(columns=["brand"], inplace=True)

                merged.rename(columns={"sale_unit": "SALE UNIT"}, inplace=True)
                merged["SALE UNIT"] = pd.to_numeric(merged["SALE UNIT"], errors="coerce").fillna(0)
                return_reason_cols = [col for col in merged.columns if col not in ["MY SKU", "SALE UNIT", "RETURN TOTAL", "RETURN %"]]
                for col in return_reason_cols:
                    merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0)
                merged["RETURN TOTAL"] = merged[return_reason_cols].sum(axis=1)

                merged["RETURN %"] = np.where(
                    merged["SALE UNIT"] > 0,
                    (merged["RETURN TOTAL"] / merged["SALE UNIT"] * 100).round(2),
                    0.0,
                )

                core_cols = ["MY SKU", "SALE UNIT", "RETURN TOTAL", "RETURN %"]
                other_cols = [col for col in merged.columns if col not in core_cols]
                merged = merged[core_cols + other_cols]

                # Add Grand Total row
                # Bug 8 fix: Exclude RETURN % from numeric sum since it's recalculated below
                numeric_cols = [
                    c
                    for c in merged.select_dtypes(include=[np.number]).columns
                    if c != "RETURN %"
                ]
                total_data = {"MY SKU": "Grand Total"}
                total_data.update(merged[numeric_cols].sum())

                total_sale = total_data.get("SALE UNIT", 0)
                total_return = total_data.get("RETURN TOTAL", 0)
                total_data["RETURN %"] = (
                    (total_return / total_sale * 100).round(2)
                    if total_sale > 0
                    else 0.0
                )

                total_row = pd.DataFrame([total_data]).reindex(merged.columns, axis=1)
                merged = pd.concat([merged, total_row], ignore_index=True)

                return merged

            # Helper function for monthly pivot tables (with month)
            # Bug 7 fix: Removed unused 'sales_data' parameter - function recalculates from self.order_df anyway
            def add_sales_and_totals_monthly(pivot):
                pivot = pivot.copy()
                pivot["RETURN TOTAL"] = pivot.sum(axis=1)
                pivot.reset_index(inplace=True)
                pivot.rename(columns={"my_sku": "MY SKU"}, inplace=True)

                monthly_sales = (
                    self.order_df.groupby(["month", "my_sku"])["qty"].sum().reset_index()
                )
                monthly_sales = monthly_sales.rename(columns={"qty": "sale_unit"})

                merged = pd.merge(
                    monthly_sales,
                    pivot,
                    left_on=["month", "my_sku"],
                    right_on=["month", "MY SKU"],
                    how="outer",
                )

                if "my_sku" in merged.columns:
                    merged["MY SKU"] = merged["MY SKU"].fillna(merged["my_sku"])
                    merged.drop(columns=["my_sku"], inplace=True)

                merged.rename(columns={"sale_unit": "SALE UNIT"}, inplace=True)
                merged["SALE UNIT"] = pd.to_numeric(merged["SALE UNIT"], errors="coerce").fillna(0)
                return_reason_cols = [col for col in merged.columns if col not in ["month", "MY SKU", "SALE UNIT", "RETURN TOTAL", "RETURN %"]]
                for col in return_reason_cols:
                    merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0)
                merged["RETURN TOTAL"] = merged[return_reason_cols].sum(axis=1)

                merged["RETURN %"] = np.where(
                    merged["SALE UNIT"] > 0,
                    (merged["RETURN TOTAL"] / merged["SALE UNIT"] * 100).round(2),
                    0.0,
                )

                core_cols = ["month", "MY SKU", "SALE UNIT", "RETURN TOTAL", "RETURN %"]
                other_cols = [col for col in merged.columns if col not in core_cols]
                merged = merged[core_cols + other_cols]

                return merged

            # Generate final pivot tables (without month)
            pivot_all_brands_final = add_sales_and_totals(
                pivot_all_brands, all_brands_sales
            )
            brandwise_pivots_final = {}
            for brand, pivot in brandwise_pivots.items():
                brand_sales = sales_summary[sales_summary["brand"] == brand]
                brandwise_pivots_final[brand] = add_sales_and_totals(pivot, brand_sales)

            # Generate final pivot tables (with month)
            if "month" in self.return_df.columns and not pivot_all_brands_monthly.empty:
                pivot_all_brands_monthly_final = add_sales_and_totals_monthly(
                    pivot_all_brands_monthly
                )
                brandwise_pivots_monthly_final = {}
                for brand, pivot in brandwise_pivots_monthly.items():
                    if not pivot.empty:
                        brand_sales = sales_summary[sales_summary["brand"] == brand]
                        brandwise_pivots_monthly_final[brand] = (
                            add_sales_and_totals_monthly(pivot)
                        )
            else:
                pivot_all_brands_monthly_final = pd.DataFrame()
                brandwise_pivots_monthly_final = {}

            self.set_progress_text("Creating Excel file...")

            # Generate output filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = (
                Path(self.output_folder.get())
                / f"SALE_RETURN_ANALYSIS_{timestamp}.xlsx"
            )

            # Write to Excel with all sheets including advanced analysis
            with pd.ExcelWriter(str(output_file), engine="xlsxwriter") as writer:
                # Get workbook object for formatting
                workbook = writer.book

                self.set_progress_text("Creating Summary sheet...")
                self.create_summary_sheet(
                    writer, workbook, sales_summary, all_brands_sales
                )

                self.set_progress_text("Creating SKU Detailed Analysis...")
                self.create_sku_detailed_sheet(writer, workbook)

                self.set_progress_text("Creating Monthly SKU Analysis...")
                self.create_monthwise_sku_sheet(writer, workbook, sales_summary)

                self.set_progress_text("Creating Monthly Summary...")
                self.create_monthwise_summary_sheet(writer, workbook, sales_summary)

                self.set_progress_text("Creating Status Reason Monthly...")
                self.create_status_reason_monthly_sheet(writer, workbook)

                self.set_progress_text("Creating SKU Comparison Analysis...")
                self.create_sku_comparison_sheet(writer, workbook, sales_summary)

                self.set_progress_text("Creating Advanced Analytics...")
                self.create_quarterly_analysis_sheet(writer, workbook, sales_summary)
                self.create_seasonal_trends_sheet(writer, workbook, sales_summary)
                self.create_brand_performance_sheet(writer, workbook, sales_summary)
                self.create_category_performance_sheet(writer, workbook)
                self.create_product_lifecycle_sheet(writer, workbook, sales_summary)
                self.create_return_analysis_sheet(writer, workbook, sales_summary)
                self.create_financial_impact_sheet(writer, workbook, sales_summary)

                self.set_progress_text("Creating brand analysis sheets...")

                # Write main pivot tables (without month)
                pivot_all_brands_final.to_excel(
                    writer, sheet_name="All Brands", index=False
                )

                # Write monthly pivot tables (with month) only if they have data
                if not pivot_all_brands_monthly_final.empty:
                    pivot_all_brands_monthly_final.to_excel(
                        writer, sheet_name="All Brands Monthly", index=False
                    )

                # Format styles for pivot sheets
                # Bug 5 fix: Values are already scaled (e.g., 15.50 = 15.50%), so use plain number format
                # Previously used "0.0%" which multiplied by 100 again in Excel
                percent_format = workbook.add_format({"num_format": "0.00"})
                red_text_format = workbook.add_format({"font_color": "red"})

                # Format All Brands sheet
                worksheet = writer.sheets["All Brands"]
                self.format_worksheet(
                    worksheet, pivot_all_brands_final, percent_format, red_text_format
                )

                # Format All Brands Monthly sheet only if it exists
                if not pivot_all_brands_monthly_final.empty:
                    worksheet = writer.sheets["All Brands Monthly"]
                    self.format_worksheet(
                        worksheet,
                        pivot_all_brands_monthly_final,
                        percent_format,
                        red_text_format,
                    )

                existing_sheet_names = set(writer.sheets.keys())

                # Process brand sheets (without month)
                for brand, pivot in brandwise_pivots_final.items():
                    sheet_name = self.make_safe_sheet_name(brand, existing_sheet_names)
                    pivot.to_excel(writer, sheet_name=sheet_name, index=False)
                    worksheet = writer.sheets[sheet_name]
                    self.format_worksheet(
                        worksheet, pivot, percent_format, red_text_format
                    )

                # Process brand sheets (with month)
                for brand, pivot in brandwise_pivots_monthly_final.items():
                    sheet_name = self.make_safe_sheet_name(brand, existing_sheet_names, suffix=" Monthly")
                    pivot.to_excel(writer, sheet_name=sheet_name, index=False)
                    worksheet = writer.sheets[sheet_name]
                    self.format_worksheet(
                        worksheet, pivot, percent_format, red_text_format
                    )

            self.set_progress_text("Analysis completed successfully!")

            # Generate results summary
            total_sales = all_brands_sales["sale_unit"].sum()
            total_returns = self.return_df["quantity"].sum()
            return_rate = (total_returns / total_sales * 100) if total_sales > 0 else 0
            category_sheet_line = (
                "\n• Category Performance (Category Trends & Return Reasons)"
                if self.category_sheet_created
                else ""
            )

            results_text = f"""=== ANALYSIS COMPLETED SUCCESSFULLY! ===

OUTPUT FILE: {output_file.name}
LOCATION: {output_file.parent}

SUMMARY STATISTICS:
========================================================
Total Sales Units: {total_sales:,}
Total Return Units: {total_returns:,}
Overall Return Rate: {return_rate:.2f}%

BRANDS ANALYZED: {len(sales_summary["brand"].unique())}
========================================================
{
                chr(10).join(
                    [
                        f"• {brand}: {sales_summary[sales_summary['brand'] == brand]['sale_unit'].sum():,} units"
                        for brand in sorted(sales_summary["brand"].unique())
                    ]
                )
            }

SHEETS CREATED:
========================================================
• Summary (Overall Analysis & Insights)
• SKU Detailed Analysis (Status-wise Sales & Returns)
• Monthly SKU Analysis (Month-wise SKU Performance)
• Monthly Summary (Month-by-month Breakdown)
• SKU Month Comparison (Month-to-Month Changes Analysis)
• Quarterly Analysis (Q1, Q2, Q3, Q4 Performance)
• Seasonal Trends (Peak/Low Months & Seasonality)
• Brand Performance (Ranking & Market Share)
{category_sheet_line}
• Product Lifecycle (Growth/Decline Stages)
• Return Analysis (High-Risk SKUs & Quality Scores)
• Financial Impact (Revenue Loss & Cost Analysis)
• All Brands (Combined Analysis - Without Month)
• All Brands Monthly (Combined Analysis - With Month)
{
                chr(10).join(
                    [
                        f"• {brand} (Brand-specific Analysis - Without Month)"
                        for brand in sorted(brandwise_pivots_final.keys())
                    ]
                )
            }
{
                chr(10).join(
                    [
                        f"• {brand} Monthly (Brand-specific Analysis - With Month)"
                        for brand in sorted(brandwise_pivots_monthly_final.keys())
                    ]
                )
            }

RETURN REASONS ANALYZED: {len(self.return_df["return_reason"].unique())}
========================================================
{
                chr(10).join(
                    [
                        f"• {reason}: {self.return_df[self.return_df['return_reason'] == reason]['quantity'].sum():,} units"
                        for reason in self.return_df["return_reason"]
                        .value_counts()
                        .head(10)
                        .index
                    ]
                )
            }

Analysis completed at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
File saved successfully and ready to open!"""

            self.set_results_text_threadsafe(results_text)

            # Show completion message
            self.run_on_main_thread(
                lambda: messagebox.showinfo(
                    "Success",
                    f"Analysis completed successfully!\n\nFile saved as:\n{output_file.name}\n\nLocation:\n{output_file.parent}",
                )
            )

        except Exception as e:
            error_msg = f"Analysis failed with error:\n{str(e)}"
            self.set_progress_text("Analysis failed")
            self.run_on_main_thread(lambda: messagebox.showerror("Error", error_msg))
            self.set_results_text_threadsafe(f"ERROR: {error_msg}")
        finally:
            self.analysis_running = False
            self.set_progress_running(False)
            self.set_controls_enabled(True)

    def create_summary_sheet(self, writer, workbook, sales_summary, all_brands_sales):
        """Create Summary Sheet with exact formatting"""
        summary_worksheet = workbook.add_worksheet("Summary")

        # Define formats
        header_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "bg_color": "#fafd88",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        subheader_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "bg_color": "#e7fd88",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        data_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter"}
        )
        number_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter"}
        )

        # Calculate overall metrics
        total_sales = all_brands_sales["sale_unit"].sum()
        total_returns = self.return_df["quantity"].sum()
        overall_return_rate = (
            (total_returns / total_sales * 100) if total_sales > 0 else 0
        )

        def build_category_summary(order_frame, return_frame):
            if "category" not in order_frame.columns:
                return pd.DataFrame()
            sales = (
                order_frame.groupby("category", dropna=False)["qty"]
                .sum()
                .reset_index(name="sale_unit")
            )
            returns = (
                return_frame.groupby("category", dropna=False)["quantity"]
                .sum()
                .reset_index(name="return_total")
                if "category" in return_frame.columns
                else pd.DataFrame(columns=["category", "return_total"])
            )
            merged = pd.merge(sales, returns, on="category", how="outer")
            merged["sale_unit"] = pd.to_numeric(merged["sale_unit"], errors="coerce").fillna(0)
            merged["return_total"] = pd.to_numeric(merged["return_total"], errors="coerce").fillna(0)
            merged["return_rate"] = np.where(
                merged["sale_unit"] > 0,
                (merged["return_total"] / merged["sale_unit"]) * 100,
                0,
            )
            merged["category"] = merged["category"].fillna("Unknown")
            return merged.sort_values(["sale_unit", "category"], ascending=[False, True]).reset_index(drop=True)

        # Set column widths
        summary_worksheet.set_column("A:A", 35)
        summary_worksheet.set_column("B:D", 15)

        # OVERALL METRICS section
        summary_worksheet.merge_range("A1:B1", "OVERALL METRICS", header_format)
        summary_worksheet.write("A2", "Total Sales Units", data_format)
        summary_worksheet.write("B2", total_sales, number_format)
        summary_worksheet.write("A3", "Total Return Units", data_format)
        summary_worksheet.write("B3", total_returns, number_format)
        summary_worksheet.write("A4", "Overall Return Rate (%)", data_format)
        summary_worksheet.write("B4", f"{overall_return_rate:.2f}%", number_format)

        # BRAND WISE SUMMARY section
        row = 6
        summary_worksheet.merge_range(
            f"A{row}:D{row}", "BRAND WISE SUMMARY", header_format
        )
        row += 1
        summary_worksheet.write(f"A{row}", "BRAND", subheader_format)
        summary_worksheet.write(f"B{row}", "SALES UNITS", subheader_format)
        summary_worksheet.write(f"C{row}", "RETURN UNITS", subheader_format)
        summary_worksheet.write(f"D{row}", "RETURN RATE (%)", subheader_format)

        row += 1
        for brand in sorted(sales_summary["brand"].unique()):
            brand_sales = sales_summary[sales_summary["brand"] == brand][
                "sale_unit"
            ].sum()
            brand_returns = self.return_df[self.return_df["brand"] == brand][
                "quantity"
            ].sum()
            brand_return_rate = (
                (brand_returns / brand_sales * 100) if brand_sales > 0 else 0
            )

            summary_worksheet.write(f"A{row}", brand, data_format)
            summary_worksheet.write(f"B{row}", brand_sales, number_format)
            summary_worksheet.write(f"C{row}", brand_returns, number_format)
            summary_worksheet.write(
                f"D{row}", f"{brand_return_rate:.2f}%", number_format
            )
            row += 1

        category_summary = build_category_summary(self.order_df, self.return_df)
        if not category_summary.empty:
            row += 1
            summary_worksheet.merge_range(
                f"A{row}:D{row}", "CATEGORY WISE SUMMARY", header_format
            )
            row += 1
            summary_worksheet.write(f"A{row}", "CATEGORY", subheader_format)
            summary_worksheet.write(f"B{row}", "SALES UNITS", subheader_format)
            summary_worksheet.write(f"C{row}", "RETURN UNITS", subheader_format)
            summary_worksheet.write(f"D{row}", "RETURN RATE (%)", subheader_format)
            row += 1
            for _, category_row in category_summary.iterrows():
                summary_worksheet.write(f"A{row}", category_row["category"], data_format)
                summary_worksheet.write(f"B{row}", category_row["sale_unit"], number_format)
                summary_worksheet.write(f"C{row}", category_row["return_total"], number_format)
                summary_worksheet.write(
                    f"D{row}", f"{category_row['return_rate']:.2f}%", number_format
                )
                row += 1

        # TOP RETURN REASONS section
        row += 1
        summary_worksheet.merge_range(
            f"A{row}:C{row}", "TOP RETURN REASONS", header_format
        )
        row += 1
        summary_worksheet.write(f"A{row}", "RETURN REASON", subheader_format)
        summary_worksheet.write(f"B{row}", "TOTAL QUANTITY", subheader_format)
        summary_worksheet.write(f"C{row}", "PERCENTAGE", subheader_format)

        row += 1
        return_reasons = (
            self.return_df.groupby("return_reason")["quantity"]
            .sum()
            .sort_values(ascending=False)
        )
        for reason, qty in return_reasons.head(20).items():
            percentage = (qty / total_returns * 100) if total_returns > 0 else 0
            summary_worksheet.write(f"A{row}", reason, data_format)
            summary_worksheet.write(f"B{row}", qty, number_format)
            summary_worksheet.write(f"C{row}", f"{percentage:.2f}%", number_format)
            row += 1

        # TOP SELLING SKUs section
        row += 1
        summary_worksheet.merge_range(
            f"A{row}:D{row}", "TOP SELLING SKUs", header_format
        )
        row += 1
        summary_worksheet.write(f"A{row}", "MY SKU", subheader_format)
        summary_worksheet.write(f"B{row}", "SALES QUANTITY", subheader_format)
        summary_worksheet.write(f"C{row}", "RETURN QUANTITY", subheader_format)
        summary_worksheet.write(f"D{row}", "RETURN RATE (%)", subheader_format)

        row += 1
        # Sort SKUs by sales quantity (descending)
        top_selling_skus = all_brands_sales.sort_values("sale_unit", ascending=False)
        for _, sku_data in top_selling_skus.head(20).iterrows():
            sku = sku_data["my_sku"]
            sales_qty = sku_data["sale_unit"]
            return_qty = self.return_df[self.return_df["my_sku"] == sku][
                "quantity"
            ].sum()
            return_rate = (return_qty / sales_qty * 100) if sales_qty > 0 else 0

            summary_worksheet.write(f"A{row}", sku, data_format)
            summary_worksheet.write(f"B{row}", sales_qty, number_format)
            summary_worksheet.write(f"C{row}", return_qty, number_format)
            summary_worksheet.write(f"D{row}", f"{return_rate:.2f}%", number_format)
            row += 1

        # TOP RETURNED SKUs section
        row += 1
        summary_worksheet.merge_range(
            f"A{row}:D{row}", "TOP RETURNED SKUs", header_format
        )
        row += 1
        summary_worksheet.write(f"A{row}", "MY SKU", subheader_format)
        summary_worksheet.write(f"B{row}", "RETURN QUANTITY", subheader_format)
        summary_worksheet.write(f"C{row}", "SALES QUANTITY", subheader_format)
        summary_worksheet.write(f"D{row}", "RETURN RATE (%)", subheader_format)

        row += 1
        sku_returns = (
            self.return_df.groupby("my_sku")["quantity"]
            .sum()
            .sort_values(ascending=False)
        )
        for sku, return_qty in sku_returns.head(20).items():
            sales_qty = all_brands_sales[all_brands_sales["my_sku"] == sku][
                "sale_unit"
            ].sum()
            return_rate = (return_qty / sales_qty * 100) if sales_qty > 0 else 0

            summary_worksheet.write(f"A{row}", sku, data_format)
            summary_worksheet.write(f"B{row}", return_qty, number_format)
            summary_worksheet.write(f"C{row}", sales_qty, number_format)
            summary_worksheet.write(f"D{row}", f"{return_rate:.2f}%", number_format)
            row += 1

        # MONTH WISE SUMMARY section
        if "month" in self.order_df.columns and "month" in self.return_df.columns:
            row += 1
            summary_worksheet.merge_range(
                f"A{row}:D{row}", "MONTH WISE SUMMARY", header_format
            )
            row += 1
            summary_worksheet.write(f"A{row}", "MONTH", subheader_format)
            summary_worksheet.write(f"B{row}", "SALES UNITS", subheader_format)
            summary_worksheet.write(f"C{row}", "RETURN UNITS", subheader_format)
            summary_worksheet.write(f"D{row}", "RETURN RATE (%)", subheader_format)

            row += 1
            months = set(self.order_df["month"].dropna().unique()) | set(
                self.return_df["month"].dropna().unique()
            )
            for month in sorted(months):
                month_sales = self.order_df[self.order_df["month"] == month][
                    "qty"
                ].sum()
                month_returns = self.return_df[self.return_df["month"] == month][
                    "quantity"
                ].sum()
                month_return_rate = (
                    (month_returns / month_sales * 100) if month_sales > 0 else 0
                )

                summary_worksheet.write(f"A{row}", month, data_format)
                summary_worksheet.write(f"B{row}", month_sales, number_format)
                summary_worksheet.write(f"C{row}", month_returns, number_format)
                summary_worksheet.write(
                    f"D{row}", f"{month_return_rate:.2f}%", number_format
                )
                row += 1

    def create_sku_detailed_sheet(self, writer, workbook):
        """Create SKU Detailed Analysis Sheet"""
        worksheet = workbook.add_worksheet("SKU Detailed Analysis")

        detail_df = self.order_df.copy()
        if "order_status" not in detail_df.columns:
            return

        status_pivot = detail_df.pivot_table(
            index="my_sku",
            columns="order_status",
            values="qty",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        gross_sales = (
            detail_df.groupby("my_sku", dropna=False)["qty"]
            .sum()
            .reset_index(name="gross_sale")
        )
        final_data = pd.merge(gross_sales, status_pivot, on="my_sku", how="left").fillna(0)

        available_statuses = [
            self.normalize_status_value(status)
            for status in detail_df["order_status"].dropna().drop_duplicates().tolist()
        ]
        preferred_statuses = ["DELIVERED", "RETURN", "EXCHANGE", "RTO"]
        status_order = preferred_statuses + [
            status for status in sorted(available_statuses) if status not in preferred_statuses
        ]
        status_order = [status for status in status_order if status in final_data.columns]
        return_statuses = [status for status in status_order if self.is_return_status(status)]

        for status in status_order:
            final_data[status] = pd.to_numeric(final_data.get(status, 0), errors="coerce").fillna(0)
        final_data["gross_sale"] = pd.to_numeric(final_data["gross_sale"], errors="coerce").fillna(0)
        final_data["TOTAL_RETURNS"] = final_data[return_statuses].sum(axis=1) if return_statuses else 0

        # Define formats
        header_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "bg_color": "#4F81BD",
                "font_color": "white",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        data_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter"}
        )
        number_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter", "num_format": "0"}
        )
        percent_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter", "num_format": "0.00"}
        )

        # Set column widths
        worksheet.set_column("A:A", 15)
        worksheet.set_column("B:Z", 12)

        # Write headers and data
        headers = ["MY SKU", "GROSS SALE"]
        for status in status_order:
            headers.extend([status, f"{status} %"])
        headers.extend(["TOTAL RETURNS", "TOTAL RETURNS %"])

        # Write headers
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)

        # Sort and write data
        final_data = final_data.sort_values("gross_sale", ascending=False)

        for row, (_, data_row) in enumerate(final_data.iterrows(), 1):
            col = 0
            worksheet.write(row, col, data_row["my_sku"], data_format)
            col += 1
            worksheet.write(row, col, int(data_row["gross_sale"]), number_format)
            col += 1

            for status in status_order:
                status_qty = int(data_row.get(status, 0))
                status_percentage = (
                    (status_qty / data_row["gross_sale"] * 100)
                    if data_row["gross_sale"] > 0
                    else 0
                )
                worksheet.write(row, col, status_qty, number_format)
                col += 1
                worksheet.write(row, col, status_percentage, percent_format)
                col += 1

            total_returns = int(data_row.get("TOTAL_RETURNS", 0))
            total_returns_percentage = (
                (total_returns / data_row["gross_sale"] * 100)
                if data_row["gross_sale"] > 0
                else 0
            )
            worksheet.write(row, col, total_returns, number_format)
            col += 1
            worksheet.write(row, col, total_returns_percentage, percent_format)
            col += 1

        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, len(final_data), len(headers) - 1)

    def create_monthwise_sku_sheet(self, writer, workbook, sales_summary):
        """Create Monthly SKU Analysis Sheet"""
        if (
            "month" not in self.order_df.columns
            or "month" not in self.return_df.columns
        ):
            return  # Skip if month column doesn't exist

        worksheet = workbook.add_worksheet("Monthly SKU Analysis")

        detail_df = self.order_df.copy()
        if "order_status" not in detail_df.columns:
            return

        monthly_sales = (
            detail_df.groupby(["month", "my_sku"], dropna=False)["qty"]
            .sum()
            .reset_index(name="gross_sale")
        )
        status_pivot = detail_df.pivot_table(
            index=["month", "my_sku"],
            columns="order_status",
            values="qty",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        final_data = pd.merge(
            monthly_sales, status_pivot, on=["month", "my_sku"], how="left"
        ).fillna(0)

        available_statuses = [
            self.normalize_status_value(status)
            for status in detail_df["order_status"].dropna().drop_duplicates().tolist()
        ]
        preferred_statuses = ["DELIVERED", "RETURN", "EXCHANGE", "RTO"]
        status_order = preferred_statuses + [
            status for status in sorted(available_statuses) if status not in preferred_statuses
        ]
        status_order = [status for status in status_order if status in final_data.columns]
        return_statuses = [status for status in status_order if self.is_return_status(status)]

        for status in status_order:
            final_data[status] = pd.to_numeric(final_data.get(status, 0), errors="coerce").fillna(0)
        final_data["gross_sale"] = pd.to_numeric(final_data["gross_sale"], errors="coerce").fillna(0)
        final_data["TOTAL_RETURNS"] = final_data[return_statuses].sum(axis=1) if return_statuses else 0

        # Define formats (same as SKU detailed)
        header_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "bg_color": "#4F81BD",
                "font_color": "white",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        data_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter"}
        )
        number_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter", "num_format": "0"}
        )
        percent_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter", "num_format": "0.00"}
        )

        # Set column widths
        worksheet.set_column("A:C", 15)
        worksheet.set_column("D:Z", 12)

        # Create headers
        headers = ["MONTH", "MY SKU", "GROSS SALE"]
        for status in status_order:
            headers.extend([status, f"{status} %"])
        headers.extend(["TOTAL RETURNS", "TOTAL RETURNS %"])

        # Write headers
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)

        # Sort and write data
        final_data = final_data.sort_values(
            ["month", "gross_sale"], ascending=[True, False]
        )

        for row, (_, data_row) in enumerate(final_data.iterrows(), 1):
            col = 0
            worksheet.write(row, col, data_row["month"], data_format)
            col += 1
            worksheet.write(row, col, data_row["my_sku"], data_format)
            col += 1
            worksheet.write(row, col, int(data_row["gross_sale"]), number_format)
            col += 1

            for status in status_order:
                status_qty = int(data_row.get(status, 0))
                status_percentage = (
                    (status_qty / data_row["gross_sale"] * 100)
                    if data_row["gross_sale"] > 0
                    else 0
                )
                worksheet.write(row, col, status_qty, number_format)
                col += 1
                worksheet.write(row, col, status_percentage, percent_format)
                col += 1

            total_returns = int(data_row.get("TOTAL_RETURNS", 0))
            total_returns_percentage = (
                (total_returns / data_row["gross_sale"] * 100)
                if data_row["gross_sale"] > 0
                else 0
            )
            worksheet.write(row, col, total_returns, number_format)
            col += 1
            worksheet.write(row, col, total_returns_percentage, percent_format)
            col += 1

        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, len(final_data), len(headers) - 1)

    def create_monthwise_summary_sheet(self, writer, workbook, sales_summary):
        """Create Monthly Summary Sheet"""
        if "month" not in self.order_df.columns:
            return

        summary_worksheet = workbook.add_worksheet("Monthly Summary")
        title_format = workbook.add_format({"bold": True, "font_size": 12, "bg_color": "#4F81BD", "font_color": "white", "align": "center", "valign": "vcenter", "border": 1})
        section_format = workbook.add_format({"bold": True, "font_size": 11, "bg_color": "#D9E2F3", "align": "center", "valign": "vcenter", "border": 1})
        subheader_format = workbook.add_format({"bold": True, "bg_color": "#EEF4FB", "align": "center", "valign": "vcenter", "border": 1})
        label_format = workbook.add_format({"border": 1, "align": "left", "valign": "vcenter"})
        number_format = workbook.add_format({"border": 1, "align": "right", "valign": "vcenter", "num_format": "0"})
        percent_format = workbook.add_format({"border": 1, "align": "right", "valign": "vcenter"})

        def build_brand_summary(order_frame, return_frame):
            sales = order_frame.groupby("brand", dropna=False)["qty"].sum().reset_index(name="sale_unit")
            returns = return_frame.groupby("brand", dropna=False)["quantity"].sum().reset_index(name="return_total")
            merged = pd.merge(sales, returns, on="brand", how="outer")
            merged["sale_unit"] = pd.to_numeric(merged["sale_unit"], errors="coerce").fillna(0)
            merged["return_total"] = pd.to_numeric(merged["return_total"], errors="coerce").fillna(0)
            merged["return_rate"] = np.where(merged["sale_unit"] > 0, (merged["return_total"] / merged["sale_unit"]) * 100, 0)
            return merged.sort_values(["sale_unit", "brand"], ascending=[False, True]).reset_index(drop=True)

        def build_category_summary(order_frame, return_frame):
            if "category" not in order_frame.columns:
                return pd.DataFrame()
            sales = order_frame.groupby("category", dropna=False)["qty"].sum().reset_index(name="sale_unit")
            returns = (
                return_frame.groupby("category", dropna=False)["quantity"].sum().reset_index(name="return_total")
                if "category" in return_frame.columns
                else pd.DataFrame(columns=["category", "return_total"])
            )
            merged = pd.merge(sales, returns, on="category", how="outer")
            merged["sale_unit"] = pd.to_numeric(merged["sale_unit"], errors="coerce").fillna(0)
            merged["return_total"] = pd.to_numeric(merged["return_total"], errors="coerce").fillna(0)
            merged["return_rate"] = np.where(merged["sale_unit"] > 0, (merged["return_total"] / merged["sale_unit"]) * 100, 0)
            merged["category"] = merged["category"].fillna("Unknown")
            return merged.sort_values(["sale_unit", "category"], ascending=[False, True]).reset_index(drop=True)

        def build_sku_summary(order_frame, return_frame):
            sales = order_frame.groupby("my_sku", dropna=False)["qty"].sum().reset_index(name="sale_qty")
            returns = return_frame.groupby("my_sku", dropna=False)["quantity"].sum().reset_index(name="return_qty")
            merged = pd.merge(sales, returns, on="my_sku", how="outer")
            merged["sale_qty"] = pd.to_numeric(merged["sale_qty"], errors="coerce").fillna(0)
            merged["return_qty"] = pd.to_numeric(merged["return_qty"], errors="coerce").fillna(0)
            merged["return_rate"] = np.where(merged["sale_qty"] > 0, (merged["return_qty"] / merged["sale_qty"]) * 100, 0)
            return merged

        def write_sku_section(start_row, start_col, title, frame, qty_header, other_header, qty_col, other_col):
            summary_worksheet.merge_range(start_row, start_col, start_row, start_col + 3, title, section_format)
            start_row += 1
            for offset, header in enumerate(["MY SKU", qty_header, other_header, "RETURN RATE (%)"]):
                summary_worksheet.write(start_row, start_col + offset, header, subheader_format)
            start_row += 1
            for _, row in frame.iterrows():
                summary_worksheet.write(start_row, start_col, row["my_sku"], label_format)
                summary_worksheet.write(start_row, start_col + 1, row[qty_col], number_format)
                summary_worksheet.write(start_row, start_col + 2, row[other_col], number_format)
                summary_worksheet.write(start_row, start_col + 3, f"{row['return_rate']:.2f}%", percent_format)
                start_row += 1
            return start_row + 1

        months = self.sort_months_chronologically(self.order_df["month"].dropna().unique())
        preferred_statuses = ["RETURN", "EXCHANGE", "RTO"]
        available_statuses = []
        if "order_status" in self.return_df.columns:
            available_statuses = [
                self.normalize_status_value(status)
                for status in self.return_df["order_status"].dropna().drop_duplicates().tolist()
            ]
        status_order = preferred_statuses + [
            status for status in available_statuses if status not in preferred_statuses
        ]
        blocks = [(month, self.order_df[self.order_df["month"] == month].copy(), self.return_df[self.return_df["month"] == month].copy()) for month in months]
        blocks.append(("OVERALL", self.order_df.copy(), self.return_df.copy()))

        for block_index, (month_value, order_frame, return_frame) in enumerate(blocks):
            start_col = block_index * 5
            summary_worksheet.set_column(start_col, start_col, 24)
            summary_worksheet.set_column(start_col + 1, start_col + 3, 14)
            block_title = "OVERALL" if month_value == "OVERALL" else f"MONTH: {self.format_month_display(month_value)}"
            summary_worksheet.merge_range(0, start_col, 0, start_col + 3, block_title, title_format)

            total_sales = float(order_frame["qty"].sum()) if not order_frame.empty else 0.0
            total_returns = float(return_frame["quantity"].sum()) if not return_frame.empty else 0.0
            delivered_qty = max(total_sales - total_returns, 0.0)
            row = 2

            summary_worksheet.merge_range(row, start_col, row, start_col + 3, "OVERALL METRICS", section_format)
            row += 1
            for label, value in [("Total Sales Units", total_sales), ("Total Return Units", total_returns), ("Overall Return Rate (%)", f"{(total_returns / total_sales) * 100:.2f}%" if total_sales else "0.00%")]:
                summary_worksheet.write(row, start_col, label, label_format)
                summary_worksheet.write(row, start_col + 1, value, percent_format if isinstance(value, str) else number_format)
                row += 1
            row += 1

            summary_worksheet.merge_range(row, start_col, row, start_col + 3, "STATUS WISE SUMMARY", section_format)
            row += 1
            summary_worksheet.write(row, start_col, "STATUS", subheader_format)
            summary_worksheet.write(row, start_col + 1, "QTY", subheader_format)
            summary_worksheet.write(row, start_col + 2, "%", subheader_format)
            row += 1
            entries = [("TOTAL", total_sales, "100.0%" if total_sales else "0.0%")]
            if delivered_qty > 0:
                entries.append(("Delivered", delivered_qty, f"{(delivered_qty / total_sales) * 100:.1f}%" if total_sales else "0.0%"))
            for status in status_order:
                qty = float(return_frame.loc[return_frame["order_status"] == status, "quantity"].sum()) if not return_frame.empty else 0.0
                if qty > 0 or status in preferred_statuses:
                    entries.append((status, qty, f"{(qty / total_sales) * 100:.1f}%" if total_sales else "0.0%"))
            for label, qty, pct_text in entries:
                summary_worksheet.write(row, start_col, label, label_format)
                summary_worksheet.write(row, start_col + 1, qty, number_format)
                summary_worksheet.write(row, start_col + 2, pct_text, percent_format)
                row += 1
            row += 1

            brand_summary = build_brand_summary(order_frame, return_frame)
            summary_worksheet.merge_range(row, start_col, row, start_col + 3, "BRAND WISE SUMMARY", section_format)
            row += 1
            for offset, header in enumerate(["BRAND", "SALES UNITS", "RETURN UNITS", "RETURN RATE (%)"]):
                summary_worksheet.write(row, start_col + offset, header, subheader_format)
            row += 1
            for _, brand_row in brand_summary.iterrows():
                summary_worksheet.write(row, start_col, brand_row["brand"], label_format)
                summary_worksheet.write(row, start_col + 1, brand_row["sale_unit"], number_format)
                summary_worksheet.write(row, start_col + 2, brand_row["return_total"], number_format)
                summary_worksheet.write(row, start_col + 3, f"{brand_row['return_rate']:.2f}%", percent_format)
                row += 1
            row += 1

            category_summary = build_category_summary(order_frame, return_frame)
            if not category_summary.empty:
                summary_worksheet.merge_range(row, start_col, row, start_col + 3, "CATEGORY WISE SUMMARY", section_format)
                row += 1
                for offset, header in enumerate(["CATEGORY", "SALES UNITS", "RETURN UNITS", "RETURN RATE (%)"]):
                    summary_worksheet.write(row, start_col + offset, header, subheader_format)
                row += 1
                for _, category_row in category_summary.iterrows():
                    summary_worksheet.write(row, start_col, category_row["category"], label_format)
                    summary_worksheet.write(row, start_col + 1, category_row["sale_unit"], number_format)
                    summary_worksheet.write(row, start_col + 2, category_row["return_total"], number_format)
                    summary_worksheet.write(row, start_col + 3, f"{category_row['return_rate']:.2f}%", percent_format)
                    row += 1
                row += 1

            sku_summary = build_sku_summary(order_frame, return_frame)
            row = write_sku_section(row, start_col, "TOP SELLING SKUs", sku_summary.sort_values(["sale_qty", "return_qty", "my_sku"], ascending=[False, False, True]).head(10), "SALES QTY", "RETURN QTY", "sale_qty", "return_qty")
            row = write_sku_section(row, start_col, "TOP RETURNED SKUs", sku_summary.sort_values(["return_qty", "sale_qty", "my_sku"], ascending=[False, False, True]).head(10), "RETURN QTY", "SALES QTY", "return_qty", "sale_qty")

            summary_worksheet.merge_range(row, start_col, row, start_col + 3, "TOP RETURN REASONS", section_format)
            row += 1
            summary_worksheet.write(row, start_col, "ORDER STATUS", subheader_format)
            summary_worksheet.write(row, start_col + 1, "RETURN REASON", subheader_format)
            summary_worksheet.write(row, start_col + 2, "TOTAL QUANTITY", subheader_format)
            summary_worksheet.write(row, start_col + 3, "PERCENTAGE", subheader_format)
            row += 1
            reason_blocks = [
                ("RETURN", return_frame[return_frame["order_status"] == "RETURN"].copy()),
                ("EXCHANGE", return_frame[return_frame["order_status"] == "EXCHANGE"].copy()),
                ("RTO", return_frame[return_frame["order_status"] == "RTO"].copy()),
                ("ALL", return_frame.copy()),
            ]
            month_total_returns = float(return_frame["quantity"].sum()) if not return_frame.empty else 0.0
            for status_label, status_frame in reason_blocks:
                if status_frame.empty:
                    summary_worksheet.write(row, start_col, status_label, label_format)
                    summary_worksheet.write(row, start_col + 1, "No reasons", label_format)
                    summary_worksheet.write(row, start_col + 2, 0, number_format)
                    summary_worksheet.write(row, start_col + 3, "0.00%", percent_format)
                    row += 1
                    continue

                reason_summary = (
                    status_frame.groupby("return_reason", dropna=False)["quantity"]
                    .sum()
                    .sort_values(ascending=False)
                    .reset_index(name="total_quantity")
                )
                for _, reason_row in reason_summary.iterrows():
                    reason_pct = (reason_row["total_quantity"] / month_total_returns * 100) if month_total_returns else 0
                    summary_worksheet.write(row, start_col, status_label, label_format)
                    summary_worksheet.write(row, start_col + 1, reason_row["return_reason"], label_format)
                    summary_worksheet.write(row, start_col + 2, reason_row["total_quantity"], number_format)
                    summary_worksheet.write(row, start_col + 3, f"{reason_pct:.2f}%", percent_format)
                    row += 1
                row += 1

        summary_worksheet.freeze_panes(1, 0)
        return

        if (
            "month" not in self.order_df.columns
            or "month" not in self.return_df.columns
        ):
            return  # Skip if month column doesn't exist

        summary_worksheet = workbook.add_worksheet("Monthly Summary")

        # Define formats
        header_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "bg_color": "#fafd88",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        subheader_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "bg_color": "#e7fd88",
                "align": "left",
                "valign": "vcenter",
                "border": 1,
            }
        )
        data_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter"}
        )
        number_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter"}
        )

        # Get unique months
        months = sorted(self.order_df["month"].dropna().unique())
        cols_per_month = 5  # 4 columns for data + 1 blank column

        # Set column widths
        for month_idx in range(len(months)):
            start_col = month_idx * cols_per_month
            summary_worksheet.set_column(start_col, start_col, 35)
            summary_worksheet.set_column(start_col + 1, start_col + 3, 15)

        # Create month headers
        for month_idx, month in enumerate(months):
            start_col = month_idx * cols_per_month
            summary_worksheet.merge_range(
                0, start_col, 0, start_col + 3, f"MONTH: {month}", header_format
            )

        # Create sections for each month
        for month_idx, month in enumerate(months):
            start_col = month_idx * cols_per_month
            row = 2

            # Calculate month data
            month_sales = self.order_df[self.order_df["month"] == month]["qty"].sum()
            month_returns = self.return_df[self.return_df["month"] == month][
                "quantity"
            ].sum()
            month_return_rate = (
                (month_returns / month_sales * 100) if month_sales > 0 else 0
            )

            # OVERALL METRICS section
            summary_worksheet.merge_range(
                row, start_col, row, start_col + 1, "OVERALL METRICS", header_format
            )
            row += 1
            summary_worksheet.write(row, start_col, "Total Sales Units", data_format)
            summary_worksheet.write(row, start_col + 1, month_sales, number_format)
            row += 1
            summary_worksheet.write(row, start_col, "Total Return Units", data_format)
            summary_worksheet.write(row, start_col + 1, month_returns, number_format)
            row += 1
            summary_worksheet.write(
                row, start_col, "Overall Return Rate (%)", data_format
            )
            summary_worksheet.write(
                row, start_col + 1, f"{month_return_rate:.2f}%", number_format
            )
            row += 2

            # BRAND WISE SUMMARY
            summary_worksheet.merge_range(
                row, start_col, row, start_col + 3, "BRAND WISE SUMMARY", header_format
            )
            row += 1
            summary_worksheet.write(row, start_col, "BRAND", subheader_format)
            summary_worksheet.write(row, start_col + 1, "SALES UNITS", subheader_format)
            summary_worksheet.write(
                row, start_col + 2, "RETURN UNITS", subheader_format
            )
            summary_worksheet.write(
                row, start_col + 3, "RETURN RATE (%)", subheader_format
            )
            row += 1

            for brand in sorted(sales_summary["brand"].unique()):
                brand_month_sales = self.order_df[
                    (self.order_df["month"] == month)
                    & (self.order_df["brand"] == brand)
                ]["qty"].sum()
                brand_month_returns = self.return_df[
                    (self.return_df["month"] == month)
                    & (self.return_df["brand"] == brand)
                ]["quantity"].sum()
                brand_month_return_rate = (
                    (brand_month_returns / brand_month_sales * 100)
                    if brand_month_sales > 0
                    else 0
                )

                if brand_month_sales > 0 or brand_month_returns > 0:
                    summary_worksheet.write(row, start_col, brand, data_format)
                    summary_worksheet.write(
                        row, start_col + 1, brand_month_sales, number_format
                    )
                    summary_worksheet.write(
                        row, start_col + 2, brand_month_returns, number_format
                    )
                    summary_worksheet.write(
                        row,
                        start_col + 3,
                        f"{brand_month_return_rate:.2f}%",
                        number_format,
                    )
                    row += 1
            row += 1

            # TOP SELLING SKUs
            summary_worksheet.merge_range(
                row, start_col, row, start_col + 3, "TOP SELLING SKUs", header_format
            )
            row += 1
            summary_worksheet.write(row, start_col, "MY SKU", subheader_format)
            summary_worksheet.write(row, start_col + 1, "SALES QTY", subheader_format)
            summary_worksheet.write(row, start_col + 2, "RETURN QTY", subheader_format)
            summary_worksheet.write(
                row, start_col + 3, "RETURN RATE (%)", subheader_format
            )
            row += 1

            # Get top selling SKUs for this month
            month_sku_sales = (
                self.order_df[self.order_df["month"] == month]
                .groupby("my_sku")["qty"]
                .sum()
                .sort_values(ascending=False)
            )

            for sku, sales_qty in month_sku_sales.head(10).items():
                return_qty = self.return_df[
                    (self.return_df["month"] == month)
                    & (self.return_df["my_sku"] == sku)
                ]["quantity"].sum()
                return_rate = (return_qty / sales_qty * 100) if sales_qty > 0 else 0

                summary_worksheet.write(row, start_col, sku, data_format)
                summary_worksheet.write(row, start_col + 1, sales_qty, number_format)
                summary_worksheet.write(row, start_col + 2, return_qty, number_format)
                summary_worksheet.write(
                    row, start_col + 3, f"{return_rate:.2f}%", number_format
                )
                row += 1
            row += 1

            # TOP RETURNED SKUs
            summary_worksheet.merge_range(
                row, start_col, row, start_col + 3, "TOP RETURNED SKUs", header_format
            )
            row += 1
            summary_worksheet.write(row, start_col, "MY SKU", subheader_format)
            summary_worksheet.write(row, start_col + 1, "RETURN QTY", subheader_format)
            summary_worksheet.write(row, start_col + 2, "SALES QTY", subheader_format)
            summary_worksheet.write(
                row, start_col + 3, "RETURN RATE (%)", subheader_format
            )
            row += 1

            # Get top returned SKUs for this month
            month_sku_returns = (
                self.return_df[self.return_df["month"] == month]
                .groupby("my_sku")["quantity"]
                .sum()
                .sort_values(ascending=False)
            )

            for sku, return_qty in month_sku_returns.head(10).items():
                sales_qty = self.order_df[
                    (self.order_df["month"] == month) & (self.order_df["my_sku"] == sku)
                ]["qty"].sum()
                return_rate = (return_qty / sales_qty * 100) if sales_qty > 0 else 0

                summary_worksheet.write(row, start_col, sku, data_format)
                summary_worksheet.write(row, start_col + 1, return_qty, number_format)
                summary_worksheet.write(row, start_col + 2, sales_qty, number_format)
                summary_worksheet.write(
                    row, start_col + 3, f"{return_rate:.2f}%", number_format
                )
                row += 1
            row += 1

            # TOP RETURN REASONS
            summary_worksheet.merge_range(
                row, start_col, row, start_col + 2, "TOP RETURN REASONS", header_format
            )
            row += 1
            summary_worksheet.write(row, start_col, "RETURN REASON", subheader_format)
            summary_worksheet.write(
                row, start_col + 1, "TOTAL QUANTITY", subheader_format
            )
            summary_worksheet.write(row, start_col + 2, "PERCENTAGE", subheader_format)
            row += 1

            month_return_reasons = (
                self.return_df[self.return_df["month"] == month]
                .groupby("return_reason")["quantity"]
                .sum()
                .sort_values(ascending=False)
            )
            month_total_returns = self.return_df[self.return_df["month"] == month][
                "quantity"
            ].sum()

            for reason, qty in month_return_reasons.head(10).items():
                percentage = (
                    (qty / month_total_returns * 100) if month_total_returns > 0 else 0
                )
                summary_worksheet.write(row, start_col, reason, data_format)
                summary_worksheet.write(row, start_col + 1, qty, number_format)
                summary_worksheet.write(
                    row, start_col + 2, f"{percentage:.2f}%", number_format
                )
                row += 1

        summary_worksheet.freeze_panes(1, 0)

    def create_status_reason_monthly_sheet(self, writer, workbook):
        if "month" not in self.return_df.columns or "order_status" not in self.return_df.columns:
            return

        detail_df = self.return_df.copy()
        detail_df["status_key"] = detail_df["order_status"].apply(self.normalize_status_value)
        detail_df = detail_df[detail_df["status_key"].isin(["RETURN", "EXCHANGE", "RTO"])].copy()
        if detail_df.empty:
            return

        worksheet = workbook.add_worksheet("Status Reason Monthly")
        title_format = workbook.add_format({"bold": True, "font_size": 12, "bg_color": "#4F81BD", "font_color": "white", "align": "center", "border": 1})
        label_format = workbook.add_format({"bold": True, "bg_color": "#D9E2F3", "align": "left", "border": 1})
        month_format = workbook.add_format({"bold": True, "bg_color": "#EEF4FB", "align": "left", "border": 1})
        status_format = workbook.add_format({"bold": True, "bg_color": "#FFF2CC", "align": "left", "border": 1})
        sku_format = workbook.add_format({"bold": True, "bg_color": "#F9F9F9", "align": "left", "border": 1})
        reason_format = workbook.add_format({"border": 1, "align": "left", "indent": 1})
        number_format = workbook.add_format({"border": 1, "align": "right", "num_format": "0"})
        sku_number_format = workbook.add_format({"bold": True, "bg_color": "#F9F9F9", "border": 1, "align": "right", "num_format": "0"})
        percent_format = workbook.add_format({"border": 1, "align": "right"})

        def write_status_block(start_row, start_col, frame, title_text):
            worksheet.write(start_row, start_col, title_text, status_format)
            worksheet.write(start_row, start_col + 1, "Qty", status_format)
            worksheet.write(start_row, start_col + 2, "%", status_format)
            start_row += 1

            if frame.empty:
                worksheet.write(start_row, start_col, "No data", reason_format)
                worksheet.write(start_row, start_col + 1, 0, number_format)
                worksheet.write(start_row, start_col + 2, "0.0%", percent_format)
                start_row += 2
                return start_row

            sku_totals = frame.groupby("my_sku", dropna=False)["quantity"].sum().reset_index().sort_values(["quantity", "my_sku"], ascending=[False, True])
            for _, sku_row in sku_totals.iterrows():
                sku_total = float(sku_row["quantity"])
                worksheet.write(start_row, start_col, sku_row["my_sku"], sku_format)
                worksheet.write(start_row, start_col + 1, sku_total, sku_number_format)
                worksheet.write_blank(start_row, start_col + 2, None, sku_format)
                start_row += 1

                reason_summary = (
                    frame[frame["my_sku"] == sku_row["my_sku"]]
                    .groupby("return_reason", dropna=False)["quantity"]
                    .sum()
                    .reset_index()
                    .sort_values(["quantity", "return_reason"], ascending=[False, True])
                )
                for _, reason_row in reason_summary.iterrows():
                    qty = float(reason_row["quantity"])
                    worksheet.write(start_row, start_col, reason_row["return_reason"], reason_format)
                    worksheet.write(start_row, start_col + 1, qty, number_format)
                    worksheet.write(start_row, start_col + 2, f"{(qty / sku_total) * 100:.1f}%" if sku_total else "0.0%", percent_format)
                    start_row += 1

                start_row += 1

            return start_row

        months = self.sort_months_chronologically(detail_df["month"].dropna().unique())
        blocks = [(month, detail_df[detail_df["month"] == month].copy()) for month in months]
        blocks.append(("ALL", detail_df.copy()))

        block_width = 4
        last_col = (len(blocks) - 1) * block_width + 2
        worksheet.merge_range(0, 0, 0, last_col, "MONTH-WISE RETURN / EXCHANGE / RTO REASON SUMMARY", title_format)

        for block_index, (month_value, frame) in enumerate(blocks):
            start_col = block_index * block_width
            worksheet.set_column(start_col, start_col, 36)
            worksheet.set_column(start_col + 1, start_col + 2, 12)
            row = 2
            worksheet.write(row, start_col, "MONTH", label_format)
            row += 1
            if month_value == "ALL":
                block_title = "ALL"
            else:
                parsed_month = self.parse_month_value(month_value)
                block_title = parsed_month.strftime("%b-%y") if parsed_month else str(month_value)
            worksheet.merge_range(row, start_col, row, start_col + 2, block_title, month_format)
            row += 2

            for status_key, title_text in [("RETURN", "RETURN"), ("EXCHANGE", "EXCHANGE"), ("RTO", "RTO"), ("ALL", "ALL")]:
                subset = frame.copy() if status_key == "ALL" else frame[frame["status_key"] == status_key].copy()
                row = write_status_block(row, start_col, subset, title_text)
                row += 1

        worksheet.freeze_panes(1, 0)

    def create_sku_comparison_sheet(self, writer, workbook, sales_summary):
        """Create SKU Comparison Analysis Sheet - All Months Comparison"""
        if "month" not in self.order_df.columns:
            return  # Skip if month column doesn't exist

        worksheet = workbook.add_worksheet("SKU Month Comparison")

        # Define formats
        header_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 12,
                "bg_color": "#4F81BD",
                "font_color": "white",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        subheader_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "bg_color": "#D9E2F3",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        data_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter"}
        )
        number_format = workbook.add_format(
            {"border": 1, "align": "center", "valign": "vcenter", "num_format": "0"}
        )
        positive_format = workbook.add_format(
            {
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "num_format": "0",
                "font_color": "green",
            }
        )
        negative_format = workbook.add_format(
            {
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "num_format": "0",
                "font_color": "red",
            }
        )

        # Get unique months and sort them properly by date
        months = self.order_df["month"].dropna().unique()

        # Convert month strings to datetime for proper sorting
        from datetime import datetime

        month_dates = []
        for month in months:
            try:
                # Parse month format like "Jun-25" or "May-25"
                month_date = datetime.strptime(month, "%b-%y")
                month_dates.append((month_date, month))
            except ValueError:
                # If parsing fails, use the original string
                month_dates.append((datetime.min, month))

        # Sort by date and extract month strings
        months = [month for _, month in sorted(month_dates)]

        if len(months) < 1:
            worksheet.write("A1", "No month data available", header_format)
            return

        # Create monthly sales data for all SKUs
        monthly_sales = (
            self.order_df.groupby(["month", "my_sku", "brand"])["qty"]
            .sum()
            .reset_index()
        )

        # Get all unique SKUs
        all_skus = sorted(monthly_sales["my_sku"].unique())

        # Set column widths dynamically based on number of months
        worksheet.set_column("A:A", 25)  # SKU column
        worksheet.set_column("B:B", 15)  # Brand column

        # Calculate column positions for months and changes
        col_start = 2  # Starting from column C (index 2)
        for i, month in enumerate(months):
            worksheet.set_column(col_start + i, col_start + i, 12)  # Month columns

        # Set change columns width
        change_col_start = col_start + len(months)
        for i in range(len(months) - 1):
            worksheet.set_column(
                change_col_start + i, change_col_start + i, 15
            )  # Change columns

        # Create main header
        total_cols = (
            2 + len(months) + (len(months) - 1)
        )  # SKU + Brand + Months + Changes
        end_col = chr(ord("A") + total_cols - 1)
        worksheet.merge_range(
            f"A1:{end_col}1",
            f"SKU MONTH-WISE SALES COMPARISON - ALL MONTHS",
            header_format,
        )

        # Create column headers
        row = 2
        worksheet.write(f"A{row}", "MY SKU", subheader_format)
        worksheet.write(f"B{row}", "BRAND", subheader_format)

        # Month headers
        for i, month in enumerate(months):
            col_letter = chr(ord("C") + i)
            worksheet.write(f"{col_letter}{row}", f"{month} SALES", subheader_format)

        # Change headers (month-to-month changes)
        change_col_start_letter = chr(ord("C") + len(months))
        for i in range(len(months) - 1):
            col_letter = chr(ord(change_col_start_letter) + i)
            change_header = f"{months[i + 1]} vs {months[i]} CHANGE"
            worksheet.write(f"{col_letter}{row}", change_header, subheader_format)

        # Write data for each SKU
        row = 3
        for sku in all_skus:
            # Get brand for this SKU
            sku_data = monthly_sales[monthly_sales["my_sku"] == sku]
            brand = sku_data["brand"].iloc[0] if len(sku_data) > 0 else "Unknown"

            # Write SKU and Brand
            worksheet.write(f"A{row}", sku, data_format)
            worksheet.write(f"B{row}", brand, data_format)

            # Write sales for each month
            sku_monthly_data = {}
            for month in months:
                month_sales = sku_data[sku_data["month"] == month]["qty"].sum()
                sku_monthly_data[month] = month_sales

                col_letter = chr(ord("C") + months.index(month))
                worksheet.write(f"{col_letter}{row}", month_sales, number_format)

            # Write month-to-month changes
            for i in range(len(months) - 1):
                prev_month = months[i]
                curr_month = months[i + 1]

                prev_sales = sku_monthly_data.get(prev_month, 0)
                curr_sales = sku_monthly_data.get(curr_month, 0)
                change = curr_sales - prev_sales

                col_letter = chr(ord("C") + len(months) + i)

                # Use color formatting for positive/negative changes
                if change > 0:
                    worksheet.write(f"{col_letter}{row}", change, positive_format)
                elif change < 0:
                    worksheet.write(f"{col_letter}{row}", change, negative_format)
                else:
                    worksheet.write(f"{col_letter}{row}", change, number_format)

            row += 1

        # Add SUMMARY SECTION
        row += 2
        end_col = chr(ord("A") + 2 + len(months) + (len(months) - 1) - 1)
        worksheet.merge_range(
            f"A{row}:{end_col}{row}", "MONTHLY SUMMARY", header_format
        )
        row += 1

        # Summary headers
        worksheet.write(f"A{row}", "MONTH", subheader_format)
        worksheet.write(f"B{row}", "TOTAL SALES", subheader_format)
        worksheet.write(f"C{row}", "ACTIVE SKUs", subheader_format)
        worksheet.write(f"D{row}", "vs PREV MONTH", subheader_format)
        worksheet.write(f"E{row}", "CHANGE %", subheader_format)
        row += 1

        # Calculate and write monthly summaries
        for i, month in enumerate(months):
            month_total = monthly_sales[monthly_sales["month"] == month]["qty"].sum()
            active_skus = len(
                monthly_sales[monthly_sales["month"] == month]["my_sku"].unique()
            )

            if i > 0:
                prev_month_total = monthly_sales[
                    monthly_sales["month"] == months[i - 1]
                ]["qty"].sum()
                change = month_total - prev_month_total
                change_pct = (
                    (change / prev_month_total * 100) if prev_month_total > 0 else 0
                )
            else:
                change = 0
                change_pct = 0

            worksheet.write(f"A{row}", month, data_format)
            worksheet.write(f"B{row}", month_total, number_format)
            worksheet.write(f"C{row}", active_skus, number_format)

            if change > 0:
                worksheet.write(f"D{row}", change, positive_format)
                worksheet.write(f"E{row}", f"{change_pct:.1f}%", positive_format)
            elif change < 0:
                worksheet.write(f"D{row}", change, negative_format)
                worksheet.write(f"E{row}", f"{change_pct:.1f}%", negative_format)
            else:
                worksheet.write(f"D{row}", change, number_format)
                worksheet.write(f"E{row}", f"{change_pct:.1f}%", number_format)

            row += 1

        # Add filters and freeze panes
        worksheet.freeze_panes(2, 2)  # Freeze headers and SKU/Brand columns
        total_cols = 2 + len(months) + (len(months) - 1)
        worksheet.autofilter(1, 0, row - 1, total_cols - 1)

    def format_worksheet(self, worksheet, pivot, percent_format, red_text_format):
        """Format worksheet with percentage and red text for high return reasons"""
        # Bug 12 fix: Use safer column index lookup with try-except
        try:
            # Apply percentage format to RETURN % column
            if "RETURN %" in pivot.columns:
                col_idx = pivot.columns.get_loc("RETURN %")
                worksheet.set_column(col_idx, col_idx, None, percent_format)
        except (KeyError, ValueError):
            pass  # Skip if column not found

        # Apply red text for return reasons with high counts
        return_reason_cols = [
            col
            for col in pivot.columns
            if col not in ["MY SKU", "SALE UNIT", "RETURN TOTAL", "RETURN %"]
        ]

        for col in return_reason_cols:
            try:
                if col in pivot.columns:
                    col_idx = pivot.columns.get_loc(col)
                    col_sum = (
                        pd.to_numeric(pivot[col][:-1], errors="coerce").sum()
                        if len(pivot) > 0
                        else 0
                    )  # Exclude Grand Total
                    if col_sum >= 50:
                        worksheet.set_column(col_idx, col_idx, None, red_text_format)
                        worksheet.write(0, col_idx, col, red_text_format)
            except (KeyError, ValueError):
                pass  # Skip if column not found or other errors

        # Freeze panes
        worksheet.freeze_panes(1, 1)

    def generate_order_template(self):
        """Generate the single combined input template CSV."""
        try:
            template_dir = Path(__file__).resolve().parent
            template_source = template_dir / "TEMPLATE.csv"
            if not template_source.exists():
                template_source = template_dir / "SALE TEMPLATE.csv"
            if template_source.exists():
                template_df = pd.read_csv(template_source)
            else:
                template_df = pd.DataFrame(
                    {
                        "MONTH": ["Apr-25", "Apr-25", "Apr-25", "Apr-25"],
                        "PORTAL": ["Shopify", "Shopify", "Shopify", "Shopify"],
                        "BRAND": ["Brand_A", "Brand_A", "Brand_A", "Brand_A"],
                        "ORDER ID": ["ORDER1", "ORDER2", "ORDER3", "ORDER4"],
                        "SELLER SKU CODE": ["SKU001", "SKU002", "SKU003", "SKU004"],
                        "MY SKU": ["SKU001", "SKU002", "SKU003", "SKU004"],
                        "QTY": [1, 1, 1, 1],
                        "CATEGORY": ["KURTA", "KURTA", "TSHIRT", "PANT"],
                        "ORDER STATUS": ["DELIVERED", "RETURN", "EXCHANGE", "CANCELLED"],
                        "RETURN/EXCHANGE REASON": ["", "Damaged", "Size Issue", ""],
                        "SALE PRICE": ["", "", "", ""],
                        "COST": ["", "", "", ""],
                    }
                )

            filename = filedialog.asksaveasfilename(
                title="Save Template",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            )

            if not filename:
                return

            template_df.to_csv(filename, index=False)

            template_info = f"""TEMPLATE CREATED SUCCESSFULLY!

File saved as: {Path(filename).name}
Location: {Path(filename).parent}

TEMPLATE STRUCTURE:
==================
Columns: {len(template_df.columns)}
Sample Rows: {len(template_df)}

EXPECTED INPUT FORMAT:
- One CSV only
- Same file contains sales, returns, exchanges, and cancelled rows
- ORDER STATUS drives return derivation
- RETURN/EXCHANGE REASON is the preferred reason column
- CATEGORY is used for category-wise analysis

REQUIRED COLUMNS:
- MONTH
- BRAND
- MY SKU
- QTY
- CATEGORY
- ORDER STATUS

OPTIONAL BUT SUPPORTED:
- PORTAL
- ORDER ID
- SELLER SKU CODE
- RETURN/EXCHANGE REASON
- SALE PRICE
- COST

SAMPLE DATA PREVIEW:
{template_df.head(5).to_string(index=False)}
"""

            self.update_results_text(template_info)
            messagebox.showinfo(
                "Success",
                f"Template created successfully!\n\nSaved as: {Path(filename).name}",
            )

        except Exception as e:
            messagebox.showerror("Error", f"Failed to create template:\n{str(e)}")

    def generate_return_template(self):
        """Generate Return Sheet CSV template"""
        try:
            # Define comprehensive return sheet template structure
            return_template_data = {
                "brand": [
                    "Brand_A",
                    "Brand_B",
                    "Brand_A",
                    "Brand_C",
                    "Brand_B",
                    "Brand_A",
                    "Brand_D",
                    "Brand_C",
                    "Brand_B",
                    "Brand_A",
                    "Brand_C",
                    "Brand_D",
                    "Brand_A",
                    "Brand_B",
                    "Brand_C",
                    "Brand_D",
                    "Brand_A",
                    "Brand_B",
                    "Brand_C",
                    "Brand_D",
                ],
                "my_sku": [
                    "SKU001",
                    "SKU002",
                    "SKU001",
                    "SKU004",
                    "SKU005",
                    "SKU006",
                    "SKU007",
                    "SKU008",
                    "SKU009",
                    "SKU010",
                    "SKU011",
                    "SKU012",
                    "SKU013",
                    "SKU014",
                    "SKU015",
                    "SKU016",
                    "SKU017",
                    "SKU018",
                    "SKU019",
                    "SKU020",
                ],
                "quantity": [
                    5,
                    8,
                    3,
                    12,
                    6,
                    4,
                    15,
                    2,
                    9,
                    7,
                    6,
                    10,
                    3,
                    8,
                    5,
                    11,
                    4,
                    7,
                    9,
                    6,
                ],
                "return_reason": [
                    "Defective",
                    "Wrong Size",
                    "Damaged",
                    "Not as Described",
                    "Customer Changed Mind",
                    "Quality Issues",
                    "Late Delivery",
                    "Wrong Item Sent",
                    "Defective",
                    "Wrong Size",
                    "Damaged",
                    "Not as Described",
                    "Customer Changed Mind",
                    "Quality Issues",
                    "Late Delivery",
                    "Wrong Item Sent",
                    "Defective",
                    "Wrong Size",
                    "Damaged",
                    "Quality Issues",
                ],
                "order_status": [
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                    "Delivered",
                ],
                "month": [
                    "2024-01",
                    "2024-01",
                    "2024-01",
                    "2024-01",
                    "2024-01",
                    "2024-02",
                    "2024-02",
                    "2024-02",
                    "2024-02",
                    "2024-02",
                    "2024-03",
                    "2024-03",
                    "2024-03",
                    "2024-03",
                    "2024-03",
                    "2024-04",
                    "2024-04",
                    "2024-04",
                    "2024-04",
                    "2024-04",
                ],
                "customer_id": [
                    "CUST001",
                    "CUST002",
                    "CUST003",
                    "CUST004",
                    "CUST005",
                    "CUST001",
                    "CUST006",
                    "CUST007",
                    "CUST002",
                    "CUST008",
                    "CUST003",
                    "CUST009",
                    "CUST010",
                    "CUST004",
                    "CUST011",
                    "CUST005",
                    "CUST012",
                    "CUST006",
                    "CUST013",
                    "CUST007",
                ],
                "return_value": [
                    2500,
                    6000,
                    1200,
                    14400,
                    3600,
                    1400,
                    13500,
                    560,
                    7200,
                    7700,
                    2700,
                    6500,
                    1650,
                    5600,
                    2125,
                    11000,
                    1280,
                    5950,
                    5220,
                    4500,
                ],
                "processing_cost": [
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                ],
                "category": [
                    "Electronics",
                    "Clothing",
                    "Home",
                    "Electronics",
                    "Clothing",
                    "Home",
                    "Electronics",
                    "Clothing",
                    "Home",
                    "Electronics",
                    "Clothing",
                    "Home",
                    "Electronics",
                    "Clothing",
                    "Home",
                    "Electronics",
                    "Clothing",
                    "Home",
                    "Electronics",
                    "Clothing",
                ],
                "supplier": [
                    "Supplier_1",
                    "Supplier_2",
                    "Supplier_3",
                    "Supplier_1",
                    "Supplier_2",
                    "Supplier_3",
                    "Supplier_4",
                    "Supplier_2",
                    "Supplier_3",
                    "Supplier_1",
                    "Supplier_2",
                    "Supplier_4",
                    "Supplier_1",
                    "Supplier_2",
                    "Supplier_3",
                    "Supplier_4",
                    "Supplier_1",
                    "Supplier_2",
                    "Supplier_3",
                    "Supplier_4",
                ],
                "region": [
                    "North",
                    "South",
                    "East",
                    "West",
                    "North",
                    "South",
                    "East",
                    "West",
                    "North",
                    "South",
                    "East",
                    "West",
                    "North",
                    "South",
                    "East",
                    "West",
                    "North",
                    "South",
                    "East",
                    "West",
                ],
                "city": [
                    "Delhi",
                    "Mumbai",
                    "Kolkata",
                    "Pune",
                    "Delhi",
                    "Chennai",
                    "Bangalore",
                    "Pune",
                    "Delhi",
                    "Mumbai",
                    "Kolkata",
                    "Pune",
                    "Delhi",
                    "Chennai",
                    "Bangalore",
                    "Pune",
                    "Delhi",
                    "Mumbai",
                    "Kolkata",
                    "Chennai",
                ],
                "return_date": [
                    "2024-01-20",
                    "2024-01-25",
                    "2024-01-28",
                    "2024-01-30",
                    "2024-02-02",
                    "2024-02-08",
                    "2024-02-12",
                    "2024-02-18",
                    "2024-02-22",
                    "2024-02-28",
                    "2024-03-05",
                    "2024-03-12",
                    "2024-03-18",
                    "2024-03-22",
                    "2024-03-28",
                    "2024-04-08",
                    "2024-04-12",
                    "2024-04-18",
                    "2024-04-22",
                    "2024-04-28",
                ],
                "processing_time_days": [
                    2,
                    3,
                    1,
                    4,
                    2,
                    3,
                    2,
                    1,
                    3,
                    2,
                    1,
                    4,
                    2,
                    3,
                    1,
                    2,
                    3,
                    1,
                    4,
                    2,
                ],
                "refund_status": [
                    "Completed",
                    "Completed",
                    "Pending",
                    "Completed",
                    "Completed",
                    "Completed",
                    "Completed",
                    "Pending",
                    "Completed",
                    "Completed",
                    "Completed",
                    "Completed",
                    "Pending",
                    "Completed",
                    "Completed",
                    "Completed",
                    "Completed",
                    "Pending",
                    "Completed",
                    "Completed",
                ],
            }

            # Create DataFrame
            template_df = pd.DataFrame(return_template_data)

            # Ask user where to save
            filename = filedialog.asksaveasfilename(
                title="Save Return Sheet Template",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            )

            if filename:
                template_df.to_csv(filename, index=False)

                # Show template info
                template_info = f"""RETURN SHEET TEMPLATE CREATED SUCCESSFULLY!

File saved as: {Path(filename).name}
Location: {Path(filename).parent}

COMPREHENSIVE TEMPLATE STRUCTURE:
================================
Columns: {len(template_df.columns)}
Sample Rows: {len(template_df)}

REQUIRED COLUMNS:
• brand: Product brand name (must match order sheet)
• my_sku: Unique SKU identifier (must match order sheet)
• quantity: Quantity returned
• return_reason: Reason for return
• order_status: Original order status
• month: Month in YYYY-MM format

OPTIONAL COLUMNS FOR ADVANCED ANALYTICS:
• customer_id: Customer identifier for customer analysis
• return_value: Financial value of returned items
• processing_cost: Cost to process the return
• category: Product category for category analysis
• supplier: Supplier name for supplier quality tracking
• region: Geographic region for regional analysis
• city: City for location-based analysis
• return_date: Return date for trend analysis
• processing_time_days: Days taken to process return
• refund_status: Status of refund (Completed, Pending, etc.)

SAMPLE DATA PREVIEW:
{template_df.head(5).to_string(index=False)}

COMPREHENSIVE RETURN REASONS:
============================
Quality Issues:
• Defective - Product not working properly
• Damaged - Product damaged during shipping
• Quality Issues - Poor product quality
• Wrong Item Sent - Incorrect product shipped

Customer Preference:
• Wrong Size - Size doesn't fit
• Customer Changed Mind - No longer wanted
• Not as Described - Product different from description

Service Issues:
• Late Delivery - Delivered after expected date
• Poor Packaging - Inadequate packaging

FEATURES ENABLED BY THIS TEMPLATE:
=================================
✅ Basic Return Analysis: Return rates & reasons
✅ Monthly Return Trends: Month-to-month patterns
✅ Seasonal Return Analysis: Peak return periods
✅ Customer Return Behavior: Frequent returners
✅ Financial Impact Analysis: Revenue loss calculation
✅ Quality Control: Supplier & product quality tracking
✅ Geographic Analysis: Regional return patterns
✅ Processing Efficiency: Return handling performance
✅ Risk Assessment: High-risk SKU identification
✅ Trend Analysis: Improving/worsening patterns

INSTRUCTIONS:
============
1. Replace sample data with your actual return data
2. Keep the same column names and structure
3. Add more rows as needed
4. Ensure dates are in YYYY-MM-DD format
5. Use consistent brand and SKU names matching order sheet
6. Fill required columns for basic analysis
7. Add optional columns for advanced insights
8. Use standardized return reasons for better analysis"""

                self.update_results_text(template_info)
                messagebox.showinfo(
                    "Success",
                    f"Return sheet template created successfully!\n\nSaved as: {Path(filename).name}",
                )

        except Exception as e:
            messagebox.showerror(
                "Error", f"Failed to create return template:\n{str(e)}"
            )

    def clear_all(self):
        self.order_file_path.set("")
        if getattr(self, "return_file_path", None) is not None:
            self.return_file_path.set("")
        self.output_folder.set(str(Path.home() / "Desktop"))
        self.order_df = None
        self.return_df = None
        self.files_valid = False
        self.analyze_button.config(state="disabled")
        self.update_info_text("Files cleared. Please select new files to analyze.")
        self.update_results_text("")
        self.set_progress_text("Ready to start...")

    def show_theme_selector(self):
        """Show theme selection dialog"""
        if not TTKTHEMES_AVAILABLE:
            messagebox.showinfo(
                "Theme Selector",
                "ttkthemes not installed.\nInstall with: pip install ttkthemes",
            )
            return

        # Create theme selection window
        theme_window = tk.Toplevel(self.root)
        theme_window.title("Select Theme")
        theme_window.geometry("350x400")
        theme_window.transient(self.root)
        theme_window.grab_set()

        # Center the window
        theme_window.update_idletasks()
        x = (theme_window.winfo_screenwidth() // 2) - (theme_window.winfo_width() // 2)
        y = (theme_window.winfo_screenheight() // 2) - (
            theme_window.winfo_height() // 2
        )
        theme_window.geometry(f"+{x}+{y}")

        # Theme selection frame
        frame = ttk.Frame(theme_window, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="🎨 Choose Theme", font=("Segoe UI", 14, "bold")).pack(
            pady=(0, 20)
        )

        # Available themes
        themes = [
            ("arc", "Arc - Modern blue"),
            ("equilux", "Equilux - Dark theme"),
            ("adapta", "Adapta - Material design"),
            ("breeze", "Breeze - KDE style"),
            ("yaru", "Yaru - Ubuntu style"),
            ("plastik", "Plastik - Classic"),
        ]

        selected_theme = tk.StringVar(value="arc")

        for theme_name, description in themes:
            ttk.Radiobutton(
                frame, text=description, variable=selected_theme, value=theme_name
            ).pack(anchor=tk.W, pady=3)

        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(pady=(20, 0))

        def apply_theme():
            try:
                if hasattr(self.root, "set_theme"):
                    self.root.set_theme(selected_theme.get())
                    messagebox.showinfo(
                        "Success", f"Theme '{selected_theme.get()}' applied!"
                    )
                    theme_window.destroy()
                else:
                    messagebox.showerror("Error", "Theme changing not supported.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to apply theme: {str(e)}")

        ttk.Button(button_frame, text="Apply", command=apply_theme).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        ttk.Button(button_frame, text="Cancel", command=theme_window.destroy).pack(
            side=tk.LEFT
        )

    def create_quarterly_analysis_sheet(self, writer, workbook, sales_summary):
        """Create Quarterly Performance Analysis Sheet"""
        if "month" not in self.order_df.columns:
            return

        worksheet = workbook.add_worksheet("Quarterly Analysis")

        # Define formats
        header_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 12,
                "bg_color": "#4F81BD",
                "font_color": "white",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        subheader_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "bg_color": "#D9E2F3",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        data_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter"}
        )
        number_format = workbook.add_format(
            {"border": 1, "align": "center", "valign": "vcenter", "num_format": "0"}
        )

        # Set column widths
        worksheet.set_column("A:A", 20)
        worksheet.set_column("B:H", 15)

        # Create quarter mapping function
        def get_quarter(month_str):
            month_str = str(month_str)
            if "-" not in month_str:
                return "Unknown"
            parts = month_str.split("-")
            if len(parts) != 2:
                return "Unknown"
            if len(parts[0]) == 4 and parts[0].isdigit():
                year, month_num = parts[0], int(parts[1])
            elif len(parts[0]) == 3:
                try:
                    dt = datetime.strptime(month_str, "%b-%y")
                    year, month_num = str(dt.year), dt.month
                except ValueError:
                    return "Unknown"
            else:
                return "Unknown"
            if month_num in [1, 2, 3]:
                return f"Q1 {year}"
            elif month_num in [4, 5, 6]:
                return f"Q2 {year}"
            elif month_num in [7, 8, 9]:
                return f"Q3 {year}"
            else:
                return f"Q4 {year}"

        # Add quarter column to dataframes
        # Bug 9 fix: Check if quarter column exists, add only if missing
        if "quarter" not in self.order_df.columns:
            self.order_df["quarter"] = self.order_df["month"].apply(get_quarter)
        if "quarter" not in self.return_df.columns:
            self.return_df["quarter"] = self.return_df["month"].apply(get_quarter)

        # Main header
        worksheet.merge_range("A1:H1", "QUARTERLY PERFORMANCE ANALYSIS", header_format)

        # QUARTERLY SUMMARY
        row = 3
        worksheet.merge_range(f"A{row}:H{row}", "QUARTERLY SUMMARY", header_format)
        row += 1

        # Headers
        worksheet.write(f"A{row}", "QUARTER", subheader_format)
        worksheet.write(f"B{row}", "SALES UNITS", subheader_format)
        worksheet.write(f"C{row}", "RETURN UNITS", subheader_format)
        worksheet.write(f"D{row}", "RETURN RATE (%)", subheader_format)
        worksheet.write(f"E{row}", "UNIQUE SKUs", subheader_format)
        worksheet.write(f"F{row}", "BRANDS ACTIVE", subheader_format)
        worksheet.write(f"G{row}", "AVG SALES/SKU", subheader_format)
        worksheet.write(f"H{row}", "GROWTH %", subheader_format)
        row += 1

        # Calculate quarterly data
        quarters = sorted(self.order_df["quarter"].unique())
        quarterly_data = []

        for quarter in quarters:
            q_sales = self.order_df[self.order_df["quarter"] == quarter]["qty"].sum()
            q_returns = self.return_df[self.return_df["quarter"] == quarter][
                "quantity"
            ].sum()
            q_return_rate = (q_returns / q_sales * 100) if q_sales > 0 else 0
            q_unique_skus = self.order_df[self.order_df["quarter"] == quarter][
                "my_sku"
            ].nunique()
            q_brands = self.order_df[self.order_df["quarter"] == quarter][
                "brand"
            ].nunique()
            q_avg_sales = q_sales / q_unique_skus if q_unique_skus > 0 else 0

            quarterly_data.append(
                {
                    "quarter": quarter,
                    "sales": q_sales,
                    "returns": q_returns,
                    "return_rate": q_return_rate,
                    "unique_skus": q_unique_skus,
                    "brands": q_brands,
                    "avg_sales": q_avg_sales,
                }
            )

        # Write quarterly data with growth calculation
        for i, data in enumerate(quarterly_data):
            growth = 0
            if i > 0:
                prev_sales = quarterly_data[i - 1]["sales"]
                growth = (
                    ((data["sales"] - prev_sales) / prev_sales * 100)
                    if prev_sales > 0
                    else 0
                )

            worksheet.write(f"A{row}", data["quarter"], data_format)
            worksheet.write(f"B{row}", data["sales"], number_format)
            worksheet.write(f"C{row}", data["returns"], number_format)
            worksheet.write(f"D{row}", f"{data['return_rate']:.2f}%", data_format)
            worksheet.write(f"E{row}", data["unique_skus"], number_format)
            worksheet.write(f"F{row}", data["brands"], number_format)
            worksheet.write(f"G{row}", f"{data['avg_sales']:.0f}", number_format)
            worksheet.write(
                f"H{row}", f"{growth:.1f}%" if i > 0 else "N/A", data_format
            )
            row += 1

        # BRAND QUARTERLY PERFORMANCE
        row += 2
        worksheet.merge_range(
            f"A{row}:H{row}", "BRAND QUARTERLY PERFORMANCE", header_format
        )
        row += 1

        # Dynamic headers for quarters
        worksheet.write(f"A{row}", "BRAND", subheader_format)
        col = 1
        for quarter in quarters:
            worksheet.write(row, col, f"{quarter} SALES", subheader_format)
            col += 1
        row += 1

        # Brand quarterly data
        for brand in sorted(sales_summary["brand"].unique()):
            worksheet.write(f"A{row}", brand, data_format)
            col = 1
            for quarter in quarters:
                brand_q_sales = self.order_df[
                    (self.order_df["quarter"] == quarter)
                    & (self.order_df["brand"] == brand)
                ]["qty"].sum()
                worksheet.write(row, col, brand_q_sales, number_format)
                col += 1
            row += 1

        worksheet.freeze_panes(1, 0)

    def create_seasonal_trends_sheet(self, writer, workbook, sales_summary):
        """Create Seasonal Trends Analysis Sheet"""
        if "month" not in self.order_df.columns:
            return

        worksheet = workbook.add_worksheet("Seasonal Trends")

        # Define formats
        header_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 12,
                "bg_color": "#4F81BD",
                "font_color": "white",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        subheader_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "bg_color": "#D9E2F3",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        data_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter"}
        )
        number_format = workbook.add_format(
            {"border": 1, "align": "center", "valign": "vcenter", "num_format": "0"}
        )
        peak_format = workbook.add_format(
            {
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "bg_color": "#90EE90",
                "bold": True,
            }
        )
        low_format = workbook.add_format(
            {
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "bg_color": "#FFB6C1",
                "bold": True,
            }
        )

        # Set column widths
        worksheet.set_column("A:A", 20)
        worksheet.set_column("B:H", 15)

        # Main header
        worksheet.merge_range("A1:H1", "SEASONAL TRENDS ANALYSIS", header_format)

        # MONTHLY PERFORMANCE TRENDS
        row = 3
        worksheet.merge_range(
            f"A{row}:H{row}", "MONTHLY PERFORMANCE TRENDS", header_format
        )
        row += 1

        # Get unique months and sort them chronologically
        months = self.sort_months_chronologically(
            self.order_df["month"].dropna().unique()
        )

        # Calculate monthly performance data
        monthly_data = []
        for month in months:
            # Calculate sales and returns for this month
            month_sales = self.order_df[self.order_df["month"] == month]["qty"].sum()
            month_returns = (
                self.return_df[self.return_df["month"] == month]["quantity"].sum()
                if "month" in self.return_df.columns
                else 0
            )
            return_rate = (month_returns / month_sales * 100) if month_sales > 0 else 0

            # Format month display
            formatted_month = self.format_month_display(month)

            monthly_data.append(
                {
                    "original_month": month,
                    "formatted_month": formatted_month,
                    "sales": month_sales,
                    "returns": month_returns,
                    "return_rate": return_rate,
                }
            )

        # Find peak and low months
        if monthly_data:
            sales_values = [m["sales"] for m in monthly_data]
            max_sales = max(sales_values)
            min_sales = min(sales_values)

            # Headers
            worksheet.write(f"A{row}", "MONTH", subheader_format)
            worksheet.write(f"B{row}", "TOTAL SALES", subheader_format)
            worksheet.write(f"C{row}", "TOTAL RETURNS", subheader_format)
            worksheet.write(f"D{row}", "RETURN RATE (%)", subheader_format)
            worksheet.write(f"E{row}", "TREND", subheader_format)
            worksheet.write(f"F{row}", "SEASONALITY", subheader_format)
            row += 1

            # Write monthly data with highlighting
            for data in monthly_data:
                cell_format = data_format
                trend = "Normal"
                seasonality = "Average"

                if data["sales"] == max_sales:
                    cell_format = peak_format
                    trend = "Peak"
                    seasonality = "High Season"
                elif data["sales"] == min_sales:
                    cell_format = low_format
                    trend = "Low"
                    seasonality = "Low Season"
                elif data["sales"] > (max_sales + min_sales) / 2:
                    trend = "Above Average"
                    seasonality = "Good Season"
                elif data["sales"] < (max_sales + min_sales) / 2:
                    trend = "Below Average"
                    seasonality = "Slow Season"

                worksheet.write(f"A{row}", data["formatted_month"], cell_format)
                worksheet.write(f"B{row}", int(data["sales"]), cell_format)
                worksheet.write(f"C{row}", int(data["returns"]), cell_format)
                worksheet.write(f"D{row}", f"{data['return_rate']:.2f}%", cell_format)
                worksheet.write(f"E{row}", trend, cell_format)
                worksheet.write(f"F{row}", seasonality, cell_format)
                row += 1

            # SEASONAL INSIGHTS
            row += 2
            worksheet.merge_range(f"A{row}:F{row}", "SEASONAL INSIGHTS", header_format)
            row += 1

            # Find peak and low months
            peak_months = [
                m["formatted_month"] for m in monthly_data if m["sales"] == max_sales
            ]
            low_months = [
                m["formatted_month"] for m in monthly_data if m["sales"] == min_sales
            ]

            worksheet.write(f"A{row}", "Peak Selling Months:", subheader_format)
            worksheet.write(f"B{row}", ", ".join(peak_months), peak_format)
            row += 1

            worksheet.write(f"A{row}", "Low Selling Months:", subheader_format)
            worksheet.write(f"B{row}", ", ".join(low_months), low_format)
            row += 1

            # Calculate seasonal variance
            avg_monthly_sales = (
                sum(sales_values) / len(sales_values) if sales_values else 0
            )
            variance = (
                sum((x - avg_monthly_sales) ** 2 for x in sales_values)
                / len(sales_values)
                if len(sales_values) > 1
                else 0
            )
            seasonality_index = (
                (variance**0.5) / avg_monthly_sales * 100
                if avg_monthly_sales > 0
                else 0
            )

            worksheet.write(f"A{row}", "Seasonality Index:", subheader_format)
            worksheet.write(f"B{row}", f"{seasonality_index:.1f}%", data_format)
            row += 1

            # Additional insights
            worksheet.write(f"A{row}", "Total Months Analyzed:", subheader_format)
            worksheet.write(f"B{row}", len(monthly_data), number_format)
            row += 1

            worksheet.write(f"A{row}", "Average Monthly Sales:", subheader_format)
            worksheet.write(f"B{row}", f"{avg_monthly_sales:.0f}", number_format)
            row += 1

            # Performance classification
            high_performers = len(
                [m for m in monthly_data if m["sales"] > avg_monthly_sales * 1.2]
            )
            low_performers = len(
                [m for m in monthly_data if m["sales"] < avg_monthly_sales * 0.8]
            )

            worksheet.write(f"A{row}", "High Performance Months:", subheader_format)
            worksheet.write(f"B{row}", high_performers, number_format)
            row += 1

            worksheet.write(f"A{row}", "Low Performance Months:", subheader_format)
            worksheet.write(f"B{row}", low_performers, number_format)
            row += 1

        else:
            # No data available
            worksheet.write(
                f"A{row}",
                "No monthly data available for seasonal analysis",
                data_format,
            )

        worksheet.freeze_panes(1, 0)

    def create_brand_performance_sheet(self, writer, workbook, sales_summary):
        """Create Comprehensive Brand Performance Analysis Sheet"""
        worksheet = workbook.add_worksheet("Brand Performance")

        # Define formats
        header_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 12,
                "bg_color": "#4F81BD",
                "font_color": "white",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        subheader_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "bg_color": "#D9E2F3",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        data_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter"}
        )
        number_format = workbook.add_format(
            {"border": 1, "align": "center", "valign": "vcenter", "num_format": "0"}
        )
        percent_format = workbook.add_format(
            {"border": 1, "align": "center", "valign": "vcenter", "num_format": "0.00%"}
        )
        rank1_format = workbook.add_format(
            {
                "border": 1,
                "align": "left",
                "valign": "vcenter",
                "bg_color": "#FFD700",
                "bold": True,
            }
        )
        rank2_format = workbook.add_format(
            {
                "border": 1,
                "align": "left",
                "valign": "vcenter",
                "bg_color": "#C0C0C0",
                "bold": True,
            }
        )
        rank3_format = workbook.add_format(
            {
                "border": 1,
                "align": "left",
                "valign": "vcenter",
                "bg_color": "#CD7F32",
                "bold": True,
            }
        )

        # Set column widths
        worksheet.set_column("A:A", 5)
        worksheet.set_column("B:B", 20)
        worksheet.set_column("C:K", 15)

        # Main header
        worksheet.merge_range(
            "A1:K1", "COMPREHENSIVE BRAND PERFORMANCE ANALYSIS", header_format
        )

        # OVERALL BRAND RANKING
        row = 3
        worksheet.merge_range(f"A{row}:K{row}", "OVERALL BRAND RANKING", header_format)
        row += 1

        # Headers
        worksheet.write(f"A{row}", "RANK", subheader_format)
        worksheet.write(f"B{row}", "BRAND", subheader_format)
        worksheet.write(f"C{row}", "TOTAL SALES", subheader_format)
        worksheet.write(f"D{row}", "TOTAL RETURNS", subheader_format)
        worksheet.write(f"E{row}", "RETURN RATE (%)", subheader_format)
        worksheet.write(f"F{row}", "UNIQUE SKUs", subheader_format)
        worksheet.write(f"G{row}", "AVG SALES/SKU", subheader_format)
        worksheet.write(f"H{row}", "MARKET SHARE (%)", subheader_format)
        worksheet.write(f"I{row}", "PERFORMANCE SCORE", subheader_format)
        worksheet.write(f"J{row}", "CATEGORY", subheader_format)
        worksheet.write(f"K{row}", "RECOMMENDATION", subheader_format)
        row += 1

        # Calculate brand performance metrics
        brand_performance = []
        total_market_sales = sales_summary["sale_unit"].sum()

        # First pass: calculate raw metrics for all brands
        for brand in sales_summary["brand"].unique():
            brand_sales = sales_summary[sales_summary["brand"] == brand][
                "sale_unit"
            ].sum()
            brand_returns = self.return_df[self.return_df["brand"] == brand][
                "quantity"
            ].sum()
            brand_return_rate = (
                (brand_returns / brand_sales * 100) if brand_sales > 0 else 0
            )
            brand_skus = sales_summary[sales_summary["brand"] == brand][
                "my_sku"
            ].nunique()
            avg_sales_per_sku = brand_sales / brand_skus if brand_skus > 0 else 0
            market_share = (
                (brand_sales / total_market_sales * 100)
                if total_market_sales > 0
                else 0
            )

            # Store raw values for second pass normalization
            brand_performance.append(
                {
                    "brand": brand,
                    "sales": brand_sales,
                    "returns": brand_returns,
                    "return_rate": brand_return_rate,
                    "unique_skus": brand_skus,
                    "avg_sales_sku": avg_sales_per_sku,
                    "market_share": market_share,
                    "raw_avg_sales_log": math.log1p(avg_sales_per_sku),
                }
            )

        # Second pass: calculate normalized performance scores
        max_sales_log = (
            max(b["raw_avg_sales_log"] for b in brand_performance)
            if brand_performance
            else 1
        )

        for bp in brand_performance:
            normalized_sales = (
                (bp["raw_avg_sales_log"] / max_sales_log * 100)
                if max_sales_log > 0
                else 50
            )
            bp["performance_score"] = (
                (bp["market_share"] * 0.4)
                + (normalized_sales * 0.3)
                + ((100 - bp["return_rate"]) * 0.3)
            )

            if bp["performance_score"] >= 80:
                bp["category"] = "Star Performer"
                bp["recommendation"] = "Expand & Invest"
            elif bp["performance_score"] >= 60:
                bp["category"] = "Good Performer"
                bp["recommendation"] = "Maintain & Optimize"
            elif bp["performance_score"] >= 40:
                bp["category"] = "Average Performer"
                bp["recommendation"] = "Improve Quality"
            else:
                bp["category"] = "Poor Performer"
                bp["recommendation"] = "Review & Action"

        # Sort by performance score
        brand_performance.sort(key=lambda x: x["performance_score"], reverse=True)

        # Write brand performance data with formulas
        start_data_row = row + 1
        for i, data in enumerate(brand_performance, 1):
            current_row = row

            # Choose format based on rank
            if i == 1:
                cell_format = rank1_format
            elif i == 2:
                cell_format = rank2_format
            elif i == 3:
                cell_format = rank3_format
            else:
                cell_format = data_format

            # A: RANK (formula to rank based on performance score)
            worksheet.write_formula(
                f"A{current_row}",
                f"=RANK(I{current_row},I${start_data_row}:I${start_data_row + len(brand_performance) - 1},0)",
                cell_format,
            )

            # B: BRAND (static value)
            worksheet.write(f"B{current_row}", data["brand"], cell_format)

            # C: TOTAL SALES (static value with formula comment)
            worksheet.write(f"C{current_row}", data["sales"], number_format)
            worksheet.write_comment(
                f"C{current_row}",
                "Formula: =SUMIF(brand_column,brand_name,sales_column)",
            )

            # D: TOTAL RETURNS (static value with formula comment)
            worksheet.write(f"D{current_row}", data["returns"], number_format)
            worksheet.write_comment(
                f"D{current_row}",
                "Formula: =SUMIF(brand_column,brand_name,returns_column)",
            )

            # E: RETURN RATE (%) (formula)
            worksheet.write_formula(
                f"E{current_row}",
                f"=IF(C{current_row}>0,D{current_row}/C{current_row}*100,0)",
                cell_format,
            )

            # F: UNIQUE SKUs (static for now, could be formula if SKU data is in separate sheet)
            worksheet.write(f"F{current_row}", data["unique_skus"], number_format)

            # G: AVG SALES/SKU (formula)
            worksheet.write_formula(
                f"G{current_row}",
                f"=IF(F{current_row}>0,C{current_row}/F{current_row},0)",
                number_format,
            )

            # H: MARKET SHARE (%) (formula)
            worksheet.write_formula(
                f"H{current_row}",
                f"=C{current_row}/SUM(C${start_data_row}:C${start_data_row + len(brand_performance) - 1})*100",
                cell_format,
            )

            # I: PERFORMANCE SCORE (formula - weighted calculation)
            worksheet.write_formula(
                f"I{current_row}",
                f"=(H{current_row}*0.4)+(G{current_row}/100*0.3)+((100-E{current_row})*0.3)",
                cell_format,
            )

            # J: CATEGORY (formula based on performance score)
            worksheet.write_formula(
                f"J{current_row}",
                f'=IF(I{current_row}>=80,"Star Performer",IF(I{current_row}>=60,"Good Performer",IF(I{current_row}>=40,"Average Performer","Poor Performer")))',
                cell_format,
            )

            # K: RECOMMENDATION (formula based on category)
            worksheet.write_formula(
                f"K{current_row}",
                f'=IF(J{current_row}="Star Performer","Expand & Invest",IF(J{current_row}="Good Performer","Maintain & Optimize",IF(J{current_row}="Average Performer","Improve Quality","Review & Action")))',
                cell_format,
            )

            row += 1

        # MONTH-WISE BRAND PERFORMANCE ANALYSIS
        if "month" in self.order_df.columns:
            row += 3

            # Get sorted months
            months = self.sort_months_chronologically(
                self.order_df["month"].dropna().unique()
            )

            # Calculate dynamic column width
            total_cols = 2 + (
                len(months) * 3
            )  # Brand + Total + (Sales, Returns, Rate per month)

            worksheet.merge_range(
                row,
                0,
                row,
                total_cols - 1,
                "MONTH-WISE BRAND PERFORMANCE",
                header_format,
            )
            row += 1

            # Create dynamic headers
            col = 0
            worksheet.write(row, col, "BRAND", subheader_format)
            col += 1
            worksheet.write(row, col, "TOTAL SALES", subheader_format)
            col += 1

            for month in months:
                formatted_month = self.format_month_display(month)
                worksheet.write(row, col, f"{formatted_month} SALES", subheader_format)
                col += 1
                worksheet.write(
                    row, col, f"{formatted_month} RETURNS", subheader_format
                )
                col += 1
                worksheet.write(row, col, f"{formatted_month} RATE%", subheader_format)
                col += 1

            row += 1

            # Write month-wise data for each brand
            for brand_data in brand_performance:
                brand = brand_data["brand"]
                col = 0

                # Choose format based on overall rank
                brand_rank = next(
                    i for i, b in enumerate(brand_performance, 1) if b["brand"] == brand
                )
                if brand_rank == 1:
                    cell_format = rank1_format
                elif brand_rank == 2:
                    cell_format = rank2_format
                elif brand_rank == 3:
                    cell_format = rank3_format
                else:
                    cell_format = data_format

                worksheet.write(row, col, brand, cell_format)
                col += 1
                worksheet.write(row, col, brand_data["sales"], number_format)
                col += 1

                # Month-wise data
                for month in months:
                    month_sales = self.order_df[
                        (self.order_df["month"] == month)
                        & (self.order_df["brand"] == brand)
                    ]["qty"].sum()
                    month_returns = (
                        self.return_df[
                            (self.return_df["month"] == month)
                            & (self.return_df["brand"] == brand)
                        ]["quantity"].sum()
                        if "month" in self.return_df.columns
                        else 0
                    )
                    month_return_rate = (
                        (month_returns / month_sales * 100) if month_sales > 0 else 0
                    )

                    worksheet.write(row, col, month_sales, number_format)
                    col += 1
                    worksheet.write(row, col, month_returns, number_format)
                    col += 1
                    worksheet.write(row, col, f"{month_return_rate:.1f}%", data_format)
                    col += 1

                row += 1

            # BRAND GROWTH ANALYSIS
            row += 2
            worksheet.merge_range(
                row, 0, row, 6, "BRAND GROWTH ANALYSIS", header_format
            )
            row += 1

            if len(months) >= 2:
                # Headers for growth analysis
                worksheet.write(row, 0, "BRAND", subheader_format)
                worksheet.write(row, 1, "FIRST MONTH", subheader_format)
                worksheet.write(row, 2, "LAST MONTH", subheader_format)
                worksheet.write(row, 3, "GROWTH", subheader_format)
                worksheet.write(row, 4, "GROWTH %", subheader_format)
                worksheet.write(row, 5, "TREND", subheader_format)
                worksheet.write(row, 6, "STATUS", subheader_format)
                row += 1

                first_month = months[0]
                last_month = months[-1]

                for brand_data in brand_performance:
                    brand = brand_data["brand"]

                    first_month_sales = self.order_df[
                        (self.order_df["month"] == first_month)
                        & (self.order_df["brand"] == brand)
                    ]["qty"].sum()
                    last_month_sales = self.order_df[
                        (self.order_df["month"] == last_month)
                        & (self.order_df["brand"] == brand)
                    ]["qty"].sum()

                    growth = last_month_sales - first_month_sales
                    growth_pct = (
                        (growth / first_month_sales * 100)
                        if first_month_sales > 0
                        else 0
                    )

                    # Determine trend and status
                    if growth_pct > 20:
                        trend = "Strong Growth"
                        status = "Expanding"
                        cell_format = rank1_format
                    elif growth_pct > 5:
                        trend = "Moderate Growth"
                        status = "Growing"
                        cell_format = rank2_format
                    elif growth_pct > -5:
                        trend = "Stable"
                        status = "Stable"
                        cell_format = data_format
                    elif growth_pct > -20:
                        trend = "Declining"
                        status = "Concerning"
                        cell_format = rank3_format
                    else:
                        trend = "Sharp Decline"
                        status = "Critical"
                        cell_format = rank3_format

                    worksheet.write(row, 0, brand, cell_format)
                    worksheet.write(row, 1, first_month_sales, number_format)
                    worksheet.write(row, 2, last_month_sales, number_format)
                    worksheet.write(row, 3, growth, number_format)
                    worksheet.write(row, 4, f"{growth_pct:.1f}%", cell_format)
                    worksheet.write(row, 5, trend, cell_format)
                    worksheet.write(row, 6, status, cell_format)
                    row += 1

        worksheet.freeze_panes(1, 0)

    def create_category_performance_sheet(self, writer, workbook):
        """Create category-level sales, return, and trend analysis."""
        self.category_sheet_created = False
        if self.order_df is None or "category" not in self.order_df.columns:
            return

        order_frame = self.order_df.copy()
        order_frame["category"] = (
            order_frame["category"].fillna("Unknown").astype(str).str.strip().replace("", "Unknown")
        )

        return_frame = self.return_df.copy()
        if "category" in return_frame.columns:
            return_frame["category"] = (
                return_frame["category"].fillna("Unknown").astype(str).str.strip().replace("", "Unknown")
            )
        else:
            return_frame["category"] = "Unknown"

        worksheet = workbook.add_worksheet("Category Performance")
        self.category_sheet_created = True

        header_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 12,
                "bg_color": "#4F81BD",
                "font_color": "white",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        subheader_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "bg_color": "#D9E2F3",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        data_format = workbook.add_format({"border": 1, "align": "left", "valign": "vcenter"})
        number_format = workbook.add_format({"border": 1, "align": "right", "valign": "vcenter", "num_format": "0"})
        percent_format = workbook.add_format({"border": 1, "align": "right", "valign": "vcenter"})

        worksheet.set_column("A:B", 22)
        worksheet.set_column("C:F", 16)

        sales_summary = (
            order_frame.groupby("category", dropna=False)["qty"].sum().reset_index(name="sales_units")
        )
        return_summary = (
            return_frame.groupby("category", dropna=False)["quantity"].sum().reset_index(name="return_units")
        )
        category_summary = pd.merge(sales_summary, return_summary, on="category", how="outer").fillna(0)
        category_summary["sales_units"] = pd.to_numeric(category_summary["sales_units"], errors="coerce").fillna(0)
        category_summary["return_units"] = pd.to_numeric(category_summary["return_units"], errors="coerce").fillna(0)
        category_summary["return_rate"] = np.where(
            category_summary["sales_units"] > 0,
            (category_summary["return_units"] / category_summary["sales_units"]) * 100,
            0,
        )
        total_sales = float(category_summary["sales_units"].sum())
        category_summary["sales_share"] = np.where(
            total_sales > 0,
            (category_summary["sales_units"] / total_sales) * 100,
            0,
        )
        category_summary = category_summary.sort_values(
            ["sales_units", "return_units", "category"],
            ascending=[False, False, True],
        ).reset_index(drop=True)

        row = 0
        worksheet.merge_range(row, 0, row, 5, "CATEGORY PERFORMANCE ANALYSIS", header_format)
        row += 3

        worksheet.merge_range(row, 0, row, 5, "OVERALL CATEGORY RANKING", header_format)
        row += 1
        for col, label in enumerate(["RANK", "CATEGORY", "SALES UNITS", "RETURN UNITS", "RETURN RATE (%)", "SALES SHARE (%)"]):
            worksheet.write(row, col, label, subheader_format)
        row += 1
        for index, category_row in category_summary.iterrows():
            worksheet.write(row, 0, index + 1, number_format)
            worksheet.write(row, 1, category_row["category"], data_format)
            worksheet.write(row, 2, category_row["sales_units"], number_format)
            worksheet.write(row, 3, category_row["return_units"], number_format)
            worksheet.write(row, 4, f"{category_row['return_rate']:.2f}%", percent_format)
            worksheet.write(row, 5, f"{category_row['sales_share']:.2f}%", percent_format)
            row += 1

        if "month" in order_frame.columns:
            row += 2
            worksheet.merge_range(row, 0, row, 4, "MONTH-WISE CATEGORY TREND", header_format)
            row += 1
            for col, label in enumerate(["MONTH", "CATEGORY", "SALES UNITS", "RETURN UNITS", "RETURN RATE (%)"]):
                worksheet.write(row, col, label, subheader_format)
            row += 1

            monthly_sales = (
                order_frame.groupby(["month", "category"], dropna=False)["qty"].sum().reset_index(name="sales_units")
            )
            monthly_returns = (
                return_frame.groupby(["month", "category"], dropna=False)["quantity"].sum().reset_index(name="return_units")
            )
            monthly_summary = pd.merge(
                monthly_sales, monthly_returns, on=["month", "category"], how="outer"
            ).fillna(0)
            monthly_summary["sales_units"] = pd.to_numeric(monthly_summary["sales_units"], errors="coerce").fillna(0)
            monthly_summary["return_units"] = pd.to_numeric(monthly_summary["return_units"], errors="coerce").fillna(0)
            monthly_summary["return_rate"] = np.where(
                monthly_summary["sales_units"] > 0,
                (monthly_summary["return_units"] / monthly_summary["sales_units"]) * 100,
                0,
            )
            monthly_summary["month_sort"] = monthly_summary["month"].apply(
                lambda value: self.parse_month_value(value) or datetime.max
            )
            monthly_summary = monthly_summary.sort_values(
                ["month_sort", "sales_units", "category"],
                ascending=[True, False, True],
            )
            for _, month_row in monthly_summary.iterrows():
                worksheet.write(row, 0, self.format_month_display(month_row["month"]), data_format)
                worksheet.write(row, 1, month_row["category"], data_format)
                worksheet.write(row, 2, month_row["sales_units"], number_format)
                worksheet.write(row, 3, month_row["return_units"], number_format)
                worksheet.write(row, 4, f"{month_row['return_rate']:.2f}%", percent_format)
                row += 1

        if not return_frame.empty:
            row += 2
            worksheet.merge_range(row, 0, row, 4, "TOP RETURN REASONS BY CATEGORY", header_format)
            row += 1
            for col, label in enumerate(["CATEGORY", "RETURN REASON", "TOTAL QUANTITY", "CATEGORY RETURN %", "OVERALL RETURN %"]):
                worksheet.write(row, col, label, subheader_format)
            row += 1

            total_returns = float(return_frame["quantity"].sum())
            category_return_totals = (
                return_frame.groupby("category", dropna=False)["quantity"].sum().to_dict()
            )
            reason_summary = (
                return_frame.groupby(["category", "return_reason"], dropna=False)["quantity"]
                .sum()
                .reset_index(name="total_quantity")
            )
            reason_summary["category_total"] = reason_summary["category"].map(category_return_totals).fillna(0)
            reason_summary["category_return_pct"] = np.where(
                reason_summary["category_total"] > 0,
                (reason_summary["total_quantity"] / reason_summary["category_total"]) * 100,
                0,
            )
            reason_summary["overall_return_pct"] = np.where(
                total_returns > 0,
                (reason_summary["total_quantity"] / total_returns) * 100,
                0,
            )
            reason_summary = reason_summary.sort_values(
                ["category", "total_quantity", "return_reason"],
                ascending=[True, False, True],
            )
            for category in sorted(reason_summary["category"].dropna().unique()):
                category_reasons = reason_summary[reason_summary["category"] == category].head(5)
                for _, reason_row in category_reasons.iterrows():
                    worksheet.write(row, 0, reason_row["category"], data_format)
                    worksheet.write(row, 1, reason_row["return_reason"], data_format)
                    worksheet.write(row, 2, reason_row["total_quantity"], number_format)
                    worksheet.write(row, 3, f"{reason_row['category_return_pct']:.2f}%", percent_format)
                    worksheet.write(row, 4, f"{reason_row['overall_return_pct']:.2f}%", percent_format)
                    row += 1
                row += 1

        worksheet.freeze_panes(1, 0)

    def create_product_lifecycle_sheet(self, writer, workbook, sales_summary):
        """Create Product Lifecycle Analysis Sheet"""
        if "month" not in self.order_df.columns:
            return

        worksheet = workbook.add_worksheet("Product Lifecycle")

        # Define formats
        header_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 12,
                "bg_color": "#4F81BD",
                "font_color": "white",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        subheader_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "bg_color": "#D9E2F3",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        data_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter"}
        )
        number_format = workbook.add_format(
            {"border": 1, "align": "center", "valign": "vcenter", "num_format": "0"}
        )
        new_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter", "bg_color": "#90EE90"}
        )
        declining_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter", "bg_color": "#FFB6C1"}
        )

        # Set column widths
        worksheet.set_column("A:A", 20)
        worksheet.set_column("B:J", 15)

        # Main header
        worksheet.merge_range("A1:J1", "PRODUCT LIFECYCLE ANALYSIS", header_format)

        # Get sorted months
        months = self.sort_months_chronologically(self.order_df["month"].unique())

        # PRODUCT LIFECYCLE STAGES
        row = 3
        worksheet.merge_range(
            f"A{row}:J{row}", "PRODUCT LIFECYCLE STAGES", header_format
        )
        row += 1

        # Headers
        worksheet.write(f"A{row}", "MY SKU", subheader_format)
        worksheet.write(f"B{row}", "BRAND", subheader_format)
        worksheet.write(f"C{row}", "FIRST MONTH", subheader_format)
        worksheet.write(f"D{row}", "LAST MONTH", subheader_format)
        worksheet.write(f"E{row}", "MONTHS ACTIVE", subheader_format)
        worksheet.write(f"F{row}", "TOTAL SALES", subheader_format)
        worksheet.write(f"G{row}", "PEAK MONTH SALES", subheader_format)
        worksheet.write(f"H{row}", "CURRENT TREND", subheader_format)
        worksheet.write(f"I{row}", "LIFECYCLE STAGE", subheader_format)
        worksheet.write(f"J{row}", "RECOMMENDATION", subheader_format)
        row += 1

        # Analyze each SKU's lifecycle
        sku_lifecycle = []

        for sku in sales_summary["my_sku"].unique():
            sku_data = self.order_df[self.order_df["my_sku"] == sku]
            if sku_data.empty:
                continue

            brand = sku_data["brand"].iloc[0]
            sku_months = sku_data["month"].unique()
            first_month = min(sku_months)
            last_month = max(sku_months)
            months_active = len(sku_months)
            total_sales = sku_data["qty"].sum()

            # Calculate monthly sales for trend analysis
            monthly_sales = []
            for month in months:
                month_sales = sku_data[sku_data["month"] == month]["qty"].sum()
                monthly_sales.append(month_sales)

            peak_sales = max(monthly_sales) if monthly_sales else 0

            # Determine trend (last 3 months vs previous 3 months)
            if len(monthly_sales) >= 6:
                recent_avg = sum(monthly_sales[-3:]) / 3
                previous_avg = sum(monthly_sales[-6:-3]) / 3
                if recent_avg > previous_avg * 1.1:
                    trend = "Growing"
                elif recent_avg < previous_avg * 0.9:
                    trend = "Declining"
                else:
                    trend = "Stable"
            else:
                trend = "Insufficient Data"

            # Determine lifecycle stage
            if months_active <= 3:
                if total_sales > 0:
                    stage = "Introduction"
                    recommendation = "Monitor Performance"
                else:
                    stage = "Failed Launch"
                    recommendation = "Discontinue"
            elif trend == "Growing":
                stage = "Growth"
                recommendation = "Invest & Scale"
            elif (
                trend == "Stable" and total_sales > sales_summary["sale_unit"].median()
            ):
                stage = "Maturity"
                recommendation = "Maintain & Optimize"
            elif trend == "Declining":
                stage = "Decline"
                recommendation = "Review or Phase Out"
            else:
                stage = "Mature"
                recommendation = "Monitor Closely"

            sku_lifecycle.append(
                {
                    "sku": sku,
                    "brand": brand,
                    "first_month": self.format_month_display(first_month),
                    "last_month": self.format_month_display(last_month),
                    "months_active": months_active,
                    "total_sales": total_sales,
                    "peak_sales": peak_sales,
                    "trend": trend,
                    "stage": stage,
                    "recommendation": recommendation,
                }
            )

        # Sort by total sales descending
        sku_lifecycle.sort(key=lambda x: x["total_sales"], reverse=True)

        # Write lifecycle data
        for data in sku_lifecycle:
            # Choose format based on stage
            if data["stage"] == "Introduction":
                cell_format = new_format
            elif data["stage"] == "Decline":
                cell_format = declining_format
            else:
                cell_format = data_format

            worksheet.write(f"A{row}", data["sku"], cell_format)
            worksheet.write(f"B{row}", data["brand"], cell_format)
            worksheet.write(f"C{row}", data["first_month"], cell_format)
            worksheet.write(f"D{row}", data["last_month"], cell_format)
            worksheet.write(f"E{row}", data["months_active"], number_format)
            worksheet.write(f"F{row}", data["total_sales"], number_format)
            worksheet.write(f"G{row}", data["peak_sales"], number_format)
            worksheet.write(f"H{row}", data["trend"], cell_format)
            worksheet.write(f"I{row}", data["stage"], cell_format)
            worksheet.write(f"J{row}", data["recommendation"], cell_format)
            row += 1

        # LIFECYCLE SUMMARY
        row += 2
        worksheet.merge_range(f"A{row}:F{row}", "LIFECYCLE SUMMARY", header_format)
        row += 1

        # Count products in each stage
        stage_counts = {}
        for data in sku_lifecycle:
            stage = data["stage"]
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

        worksheet.write(f"A{row}", "LIFECYCLE STAGE", subheader_format)
        worksheet.write(f"B{row}", "PRODUCT COUNT", subheader_format)
        worksheet.write(f"C{row}", "PERCENTAGE", subheader_format)
        row += 1

        total_products = len(sku_lifecycle)
        for stage, count in stage_counts.items():
            percentage = (count / total_products * 100) if total_products > 0 else 0
            worksheet.write(f"A{row}", stage, data_format)
            worksheet.write(f"B{row}", count, number_format)
            worksheet.write(f"C{row}", f"{percentage:.1f}%", data_format)
            row += 1

        worksheet.freeze_panes(1, 0)

    def create_return_analysis_sheet(self, writer, workbook, sales_summary):
        """Create Advanced Return Analysis Sheet"""
        worksheet = workbook.add_worksheet("Return Analysis")

        # Define formats
        header_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 12,
                "bg_color": "#4F81BD",
                "font_color": "white",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        subheader_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "bg_color": "#D9E2F3",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        data_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter"}
        )
        number_format = workbook.add_format(
            {"border": 1, "align": "center", "valign": "vcenter", "num_format": "0"}
        )
        high_risk_format = workbook.add_format(
            {
                "border": 1,
                "align": "left",
                "valign": "vcenter",
                "bg_color": "#FF6B6B",
                "font_color": "white",
            }
        )
        medium_risk_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter", "bg_color": "#FFE66D"}
        )
        low_risk_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter", "bg_color": "#4ECDC4"}
        )

        # Set column widths
        worksheet.set_column("A:A", 20)
        worksheet.set_column("B:K", 15)

        # Main header
        worksheet.merge_range("A1:K1", "ADVANCED RETURN ANALYSIS", header_format)

        # HIGH-RISK SKU IDENTIFICATION
        row = 3
        worksheet.merge_range(
            f"A{row}:K{row}", "HIGH-RISK SKU IDENTIFICATION", header_format
        )
        row += 1

        # Headers
        worksheet.write(f"A{row}", "MY SKU", subheader_format)
        worksheet.write(f"B{row}", "BRAND", subheader_format)
        worksheet.write(f"C{row}", "TOTAL SALES", subheader_format)
        worksheet.write(f"D{row}", "TOTAL RETURNS", subheader_format)
        worksheet.write(f"E{row}", "RETURN RATE (%)", subheader_format)
        worksheet.write(f"F{row}", "TOP RETURN REASON", subheader_format)
        worksheet.write(f"G{row}", "REASON COUNT", subheader_format)
        worksheet.write(f"H{row}", "RISK LEVEL", subheader_format)
        worksheet.write(f"I{row}", "QUALITY SCORE", subheader_format)
        worksheet.write(f"J{row}", "TREND", subheader_format)
        worksheet.write(f"K{row}", "ACTION REQUIRED", subheader_format)
        row += 1

        # Calculate return risk for each SKU
        sku_risk_analysis = []

        for sku in sales_summary["my_sku"].unique():
            sku_sales = sales_summary[sales_summary["my_sku"] == sku]["sale_unit"].sum()
            sku_returns = self.return_df[self.return_df["my_sku"] == sku][
                "quantity"
            ].sum()
            return_rate = (sku_returns / sku_sales * 100) if sku_sales > 0 else 0

            # Get brand
            brand = (
                sales_summary[sales_summary["my_sku"] == sku]["brand"].iloc[0]
                if len(sales_summary[sales_summary["my_sku"] == sku]) > 0
                else "Unknown"
            )

            # Find top return reason
            sku_return_reasons = self.return_df[self.return_df["my_sku"] == sku][
                "return_reason"
            ].value_counts()
            top_reason = (
                sku_return_reasons.index[0]
                if len(sku_return_reasons) > 0
                else "No Returns"
            )
            reason_count = (
                sku_return_reasons.iloc[0] if len(sku_return_reasons) > 0 else 0
            )

            # Calculate risk level
            if return_rate >= 15:
                risk_level = "HIGH RISK"
                action = "Immediate Review"
            elif return_rate >= 8:
                risk_level = "MEDIUM RISK"
                action = "Monitor Closely"
            elif return_rate >= 3:
                risk_level = "LOW RISK"
                action = "Standard Monitoring"
            else:
                risk_level = "MINIMAL RISK"
                action = "No Action Needed"

            # Quality score (inverse of return rate, scaled 0-100)
            quality_score = max(0, 100 - (return_rate * 5))

            # Trend analysis (if monthly data available)
            trend = "Stable"
            if "month" in self.return_df.columns:
                months = sorted(self.return_df["month"].unique())
                if len(months) >= 2:
                    recent_returns = self.return_df[
                        (self.return_df["my_sku"] == sku)
                        & (self.return_df["month"] == months[-1])
                    ]["quantity"].sum()
                    prev_returns = self.return_df[
                        (self.return_df["my_sku"] == sku)
                        & (self.return_df["month"] == months[-2])
                    ]["quantity"].sum()

                    if recent_returns > prev_returns * 1.5:
                        trend = "Worsening"
                    elif recent_returns < prev_returns * 0.5:
                        trend = "Improving"

            sku_risk_analysis.append(
                {
                    "sku": sku,
                    "brand": brand,
                    "sales": sku_sales,
                    "returns": sku_returns,
                    "return_rate": return_rate,
                    "top_reason": top_reason,
                    "reason_count": reason_count,
                    "risk_level": risk_level,
                    "quality_score": quality_score,
                    "trend": trend,
                    "action": action,
                }
            )

        # Sort by return rate descending
        sku_risk_analysis.sort(key=lambda x: x["return_rate"], reverse=True)

        # Write risk analysis data
        for data in sku_risk_analysis:
            # Choose format based on risk level
            if data["risk_level"] == "HIGH RISK":
                cell_format = high_risk_format
            elif data["risk_level"] == "MEDIUM RISK":
                cell_format = medium_risk_format
            elif data["risk_level"] == "LOW RISK":
                cell_format = low_risk_format
            else:
                cell_format = data_format

            worksheet.write(f"A{row}", data["sku"], cell_format)
            worksheet.write(f"B{row}", data["brand"], cell_format)
            worksheet.write(f"C{row}", data["sales"], number_format)
            worksheet.write(f"D{row}", data["returns"], number_format)
            worksheet.write(f"E{row}", f"{data['return_rate']:.2f}%", cell_format)
            worksheet.write(f"F{row}", data["top_reason"], cell_format)
            worksheet.write(f"G{row}", data["reason_count"], number_format)
            worksheet.write(f"H{row}", data["risk_level"], cell_format)
            worksheet.write(f"I{row}", f"{data['quality_score']:.0f}", cell_format)
            worksheet.write(f"J{row}", data["trend"], cell_format)
            worksheet.write(f"K{row}", data["action"], cell_format)
            row += 1

        # RETURN REASON TRENDS
        row += 2
        worksheet.merge_range(f"A{row}:F{row}", "RETURN REASON TRENDS", header_format)
        row += 1

        # Calculate return reason trends
        reason_analysis = (
            self.return_df.groupby("return_reason")
            .agg({"quantity": ["sum", "count"], "my_sku": "nunique"})
            .round(2)
        )

        reason_analysis.columns = ["Total_Quantity", "Frequency", "Unique_SKUs"]
        reason_analysis = reason_analysis.reset_index()
        reason_analysis = reason_analysis.sort_values("Total_Quantity", ascending=False)

        # Headers for reason trends
        worksheet.write(f"A{row}", "RETURN REASON", subheader_format)
        worksheet.write(f"B{row}", "TOTAL QUANTITY", subheader_format)
        worksheet.write(f"C{row}", "FREQUENCY", subheader_format)
        worksheet.write(f"D{row}", "AFFECTED SKUs", subheader_format)
        worksheet.write(f"E{row}", "AVG PER INCIDENT", subheader_format)
        worksheet.write(f"F{row}", "SEVERITY", subheader_format)
        row += 1

        total_return_qty = self.return_df["quantity"].sum()

        for _, reason_data in reason_analysis.iterrows():
            avg_per_incident = (
                reason_data["Total_Quantity"] / reason_data["Frequency"]
                if reason_data["Frequency"] > 0
                else 0
            )
            severity_pct = (
                (reason_data["Total_Quantity"] / total_return_qty * 100)
                if total_return_qty > 0
                else 0
            )

            if severity_pct >= 20:
                severity = "CRITICAL"
                cell_format = high_risk_format
            elif severity_pct >= 10:
                severity = "HIGH"
                cell_format = medium_risk_format
            elif severity_pct >= 5:
                severity = "MEDIUM"
                cell_format = low_risk_format
            else:
                severity = "LOW"
                cell_format = data_format

            worksheet.write(f"A{row}", reason_data["return_reason"], cell_format)
            worksheet.write(f"B{row}", reason_data["Total_Quantity"], number_format)
            worksheet.write(f"C{row}", reason_data["Frequency"], number_format)
            worksheet.write(f"D{row}", reason_data["Unique_SKUs"], number_format)
            worksheet.write(f"E{row}", f"{avg_per_incident:.1f}", number_format)
            worksheet.write(f"F{row}", severity, cell_format)
            row += 1

        worksheet.freeze_panes(1, 0)

    def create_financial_impact_sheet(self, writer, workbook, sales_summary):
        """Create Financial Impact Analysis Sheet"""
        worksheet = workbook.add_worksheet("Financial Impact")

        # Define formats
        header_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 12,
                "bg_color": "#4F81BD",
                "font_color": "white",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        subheader_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "bg_color": "#D9E2F3",
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        data_format = workbook.add_format(
            {"border": 1, "align": "left", "valign": "vcenter"}
        )
        currency_format = workbook.add_format(
            {
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "num_format": "₹#,##0",
            }
        )
        loss_format = workbook.add_format(
            {
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "num_format": "₹#,##0",
                "font_color": "red",
                "bold": True,
            }
        )

        # Set column widths
        worksheet.set_column("A:A", 25)
        worksheet.set_column("B:H", 18)

        # Main header
        worksheet.merge_range("A1:H1", "FINANCIAL IMPACT ANALYSIS", header_format)

        # Note: Since we don't have price data, we'll use estimated values
        # In real implementation, you would have price/cost columns in your data

        # ESTIMATED FINANCIAL IMPACT
        row = 3
        worksheet.merge_range(
            f"A{row}:H{row}", "ESTIMATED FINANCIAL IMPACT", header_format
        )
        row += 1

        worksheet.write(
            f"A{row}",
            "NOTE: Financial calculations use estimated average selling price of ₹500 per unit",
            data_format,
        )
        worksheet.write(
            f"B{row}", "Add actual price data for precise calculations", data_format
        )
        row += 2

        # Try to use actual price data from order_df, fallback to estimates when the column is blank.
        selling_price_series = (
            pd.to_numeric(self.order_df["selling_price"], errors="coerce").dropna()
            if "selling_price" in self.order_df.columns
            else pd.Series(dtype=float)
        )
        if not selling_price_series.empty:
            avg_selling_price = float(selling_price_series.mean())
            price_note = f"Using actual average selling price: ₹{avg_selling_price:.0f}"
        else:
            avg_selling_price = 500
            price_note = "NOTE: Using estimated average selling price of ₹500 per unit"

        cost_price_series = (
            pd.to_numeric(self.order_df["cost_price"], errors="coerce").dropna()
            if "cost_price" in self.order_df.columns
            else pd.Series(dtype=float)
        )
        if not cost_price_series.empty:
            return_processing_cost = max(50.0, float(cost_price_series.mean()) * 0.1)
            cost_note = f"Using 10% of avg cost as processing cost: ₹{return_processing_cost:.0f}"
        else:
            return_processing_cost = 50
            cost_note = "Using estimated processing cost of ₹50 per return"

        worksheet.write(f"A{row}", price_note, data_format)
        worksheet.write(f"B{row}", cost_note, data_format)
        row += 2

        # Calculate financial metrics
        total_sales_units = sales_summary["sale_unit"].sum()
        total_return_units = self.return_df["quantity"].sum()

        gross_revenue = total_sales_units * avg_selling_price
        return_loss = total_return_units * avg_selling_price
        processing_costs = total_return_units * return_processing_cost
        net_revenue = gross_revenue - return_loss - processing_costs

        # OVERALL FINANCIAL SUMMARY
        worksheet.merge_range(
            f"A{row}:H{row}", "OVERALL FINANCIAL SUMMARY", header_format
        )
        row += 1

        worksheet.write(f"A{row}", "METRIC", subheader_format)
        worksheet.write(f"B{row}", "VALUE", subheader_format)
        worksheet.write(f"C{row}", "PERCENTAGE", subheader_format)
        row += 1

        financial_metrics = [
            ("Gross Revenue (Estimated)", gross_revenue, 100),
            (
                "Revenue Lost to Returns",
                return_loss,
                (return_loss / gross_revenue * 100) if gross_revenue > 0 else 0,
            ),
            (
                "Return Processing Costs",
                processing_costs,
                (processing_costs / gross_revenue * 100) if gross_revenue > 0 else 0,
            ),
            (
                "Net Revenue (After Returns)",
                net_revenue,
                (net_revenue / gross_revenue * 100) if gross_revenue > 0 else 0,
            ),
            (
                "Total Financial Impact",
                return_loss + processing_costs,
                ((return_loss + processing_costs) / gross_revenue * 100)
                if gross_revenue > 0
                else 0,
            ),
        ]

        for metric, value, percentage in financial_metrics:
            value_format = (
                loss_format
                if "Lost" in metric or "Costs" in metric or "Impact" in metric
                else currency_format
            )

            worksheet.write(f"A{row}", metric, data_format)
            worksheet.write(f"B{row}", value, value_format)
            worksheet.write(f"C{row}", f"{percentage:.2f}%", data_format)
            row += 1

        # BRAND-WISE FINANCIAL IMPACT
        row += 2
        worksheet.merge_range(
            f"A{row}:H{row}", "BRAND-WISE FINANCIAL IMPACT", header_format
        )
        row += 1

        worksheet.write(f"A{row}", "BRAND", subheader_format)
        worksheet.write(f"B{row}", "GROSS REVENUE", subheader_format)
        worksheet.write(f"C{row}", "RETURN LOSS", subheader_format)
        worksheet.write(f"D{row}", "PROCESSING COST", subheader_format)
        worksheet.write(f"E{row}", "NET REVENUE", subheader_format)
        worksheet.write(f"F{row}", "LOSS %", subheader_format)
        worksheet.write(f"G{row}", "PROFITABILITY", subheader_format)
        worksheet.write(f"H{row}", "RISK LEVEL", subheader_format)
        row += 1

        # Calculate brand-wise financial impact
        for brand in sorted(sales_summary["brand"].unique()):
            brand_sales = sales_summary[sales_summary["brand"] == brand][
                "sale_unit"
            ].sum()
            brand_returns = self.return_df[self.return_df["brand"] == brand][
                "quantity"
            ].sum()

            brand_gross_revenue = brand_sales * avg_selling_price
            brand_return_loss = brand_returns * avg_selling_price
            brand_processing_cost = brand_returns * return_processing_cost
            brand_net_revenue = (
                brand_gross_revenue - brand_return_loss - brand_processing_cost
            )

            loss_percentage = (
                (
                    (brand_return_loss + brand_processing_cost)
                    / brand_gross_revenue
                    * 100
                )
                if brand_gross_revenue > 0
                else 0
            )

            # Determine profitability and risk
            if loss_percentage <= 5:
                profitability = "Excellent"
                risk_level = "Low"
            elif loss_percentage <= 10:
                profitability = "Good"
                risk_level = "Medium"
            elif loss_percentage <= 20:
                profitability = "Fair"
                risk_level = "High"
            else:
                profitability = "Poor"
                risk_level = "Critical"

            worksheet.write(f"A{row}", brand, data_format)
            worksheet.write(f"B{row}", brand_gross_revenue, currency_format)
            worksheet.write(f"C{row}", brand_return_loss, loss_format)
            worksheet.write(f"D{row}", brand_processing_cost, loss_format)
            worksheet.write(f"E{row}", brand_net_revenue, currency_format)
            worksheet.write(f"F{row}", f"{loss_percentage:.2f}%", data_format)
            worksheet.write(f"G{row}", profitability, data_format)
            worksheet.write(f"H{row}", risk_level, data_format)
            row += 1

        # COST OPTIMIZATION RECOMMENDATIONS
        row += 2
        worksheet.merge_range(
            f"A{row}:H{row}", "COST OPTIMIZATION RECOMMENDATIONS", header_format
        )
        row += 1

        recommendations = [
            "1. Focus on reducing returns for high-volume SKUs to maximize impact",
            "2. Investigate and address top return reasons to prevent future losses",
            "3. Implement quality control measures for brands with high return rates",
            "4. Consider return policy adjustments for frequently returned items",
            "5. Invest in better product descriptions to reduce 'not as described' returns",
            "6. Negotiate with suppliers on quality improvements for problem SKUs",
            "7. Implement predictive analytics to identify potential return risks early",
        ]

        for recommendation in recommendations:
            worksheet.write(f"A{row}", recommendation, data_format)
            row += 1

        worksheet.freeze_panes(1, 0)


def main():
    raise SystemExit("Run gui.py to launch the PyQt6 application.")


if __name__ == "__main__":
    main()
