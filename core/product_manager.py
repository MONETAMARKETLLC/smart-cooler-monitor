import json
import re
import tkinter as tk
from utils.logger import logger
from typing import  Optional, List
from pathlib import Path
from difflib import get_close_matches
from tkinter import messagebox, simpledialog

class ProductManager:
    """Manages product database and versioning"""
    
    def __init__(self, products_file: str = "products.json", clips_base_dir: str = "clips"):
        self.products_file = Path(products_file)
        self.clips_base_dir = Path(clips_base_dir)
        self.products = self._load_products()
        self._ensure_clips_directory()
    
    def _load_products(self) -> List[str]:
        """Load products from JSON file"""
        if not self.products_file.exists():
            return []
        
        try:
            with open(self.products_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading products file: {e}")
            return []
    
    def _save_products(self) -> None:
        """Save products to JSON file"""
        try:
            with open(self.products_file, 'w', encoding='utf-8') as f:
                json.dump(sorted(list(set(self.products))), f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error(f"Error saving products: {e}")
    
    def _ensure_clips_directory(self) -> None:
        """Ensure clips directory exists"""
        self.clips_base_dir.mkdir(exist_ok=True)
        logger.info(f"Clips directory ready: {self.clips_base_dir}")
    
    def add_product(self, product_name: str) -> bool:
        """Add a new product to the list"""
        base_product = self._extract_base_product_name(product_name)
        if base_product not in self.products:
            self.products.append(base_product)
            self._save_products()
            logger.info(f"New product added: {base_product}")
            return True
        return False
    
    def _extract_base_product_name(self, versioned_name: str) -> str:
        """Extract base product name without version suffix"""
        match = re.match(r'^(.+)_v\d+$', versioned_name)
        return match.group(1) if match else versioned_name
    
    def get_next_version(self, base_product_name: str) -> str:
        """Get next available version for a product"""
        if not self.clips_base_dir.exists():
            return f"{base_product_name}_v1"
        
        pattern = f"{base_product_name}_v*"
        existing_dirs = list(self.clips_base_dir.glob(pattern))
        
        if not existing_dirs:
            return f"{base_product_name}_v1"
        
        version_numbers = []
        for dir_path in existing_dirs:
            match = re.match(f'^{re.escape(base_product_name)}_v(\\d+)$', dir_path.name)
            if match:
                version_numbers.append(int(match.group(1)))
        
        if not version_numbers:
            return f"{base_product_name}_v1"
        
        next_version = max(version_numbers) + 1
        return f"{base_product_name}_v{next_version}"
    
    def find_similar_products(self, query: str, max_matches: int = 5) -> List[str]:
        """Find similar products using fuzzy matching"""
        if not query:
            return []
        
        base_query = self._extract_base_product_name(query)
        
        # Exact matches first
        exact_matches = [p for p in self.products if base_query.lower() in p.lower()]
        
        # Fuzzy matches
        fuzzy_matches = get_close_matches(
            base_query.lower(),
            [p.lower() for p in self.products],
            n=max_matches,
            cutoff=0.6
        )
        
        # Map back to original names
        fuzzy_original = []
        for fuzzy in fuzzy_matches:
            for product in self.products:
                if product.lower() == fuzzy:
                    fuzzy_original.append(product)
                    break
        
        # Combine and remove duplicates
        all_matches = []
        for match in exact_matches + fuzzy_original:
            if match not in all_matches:
                all_matches.append(match)
        
        return all_matches[:max_matches]
    
    def get_existing_versions(self, base_product: str) -> List[str]:
        """Get list of existing versions for a product"""
        if not self.clips_base_dir.exists():
            return []
        
        pattern = f"{base_product}_v*"
        existing_dirs = list(self.clips_base_dir.glob(pattern))
        
        versions = []
        for dir_path in existing_dirs:
            match = re.match(f'^{re.escape(base_product)}_v(\\d+)$', dir_path.name)
            if match:
                versions.append(f"v{match.group(1)}")
        
        return sorted(versions, key=lambda x: int(x[1:]))
    
    def get_product_input(self) -> Optional[str]:
        """Get product name with validation and automatic versioning"""
        root = tk.Tk()
        root.withdraw()
        
        try:
            while True:
                product_name = simpledialog.askstring(
                    "Smart Cooler - Product",
                    "Product name to record:",
                    initialvalue=""
                )
                
                if product_name is None:
                    return None
                
                product_name = product_name.strip()
                if not product_name:
                    messagebox.showwarning("Warning", "Please enter a product name")
                    continue
                
                normalized_name = product_name.lower().replace(' ', '_')
                base_product = self._extract_base_product_name(normalized_name)
                
                if base_product in [p.lower() for p in self.products]:
                    return self._handle_existing_product(base_product)
                else:
                    return self._handle_new_product(base_product, normalized_name)
        
        finally:
            root.destroy()
    
    def _handle_existing_product(self, base_product: str) -> Optional[str]:
        """Handle existing product logic"""
        versioned_name = self.get_next_version(base_product)
        existing_versions = self.get_existing_versions(base_product)
        
        version_info = f"Existing versions: {', '.join(existing_versions)}" if existing_versions else "First recording"
        
        confirm = messagebox.askyesno(
            "Existing Product",
            f"Product: {base_product}\n{version_info}\n\n"
            f"New version will be: {versioned_name}\n\nContinue?"
        )
        
        return versioned_name if confirm else None
    
    def _handle_new_product(self, base_product: str, normalized_name: str) -> Optional[str]:
        """Handle new product logic"""
        similar = self.find_similar_products(base_product)
        
        if similar:
            return self._handle_similar_products(similar, base_product)
        else:
            confirm = messagebox.askyesno(
                "New Product",
                f"'{base_product}' will be a new product.\n\nContinue?"
            )
            
            if confirm:
                new_versioned_name = f"{base_product}_v1"
                self.add_product(base_product)
                return new_versioned_name
        
        return None
    
    def _handle_similar_products(self, similar: List[str], base_product: str) -> Optional[str]:
        """Handle similar products logic"""
        suggestions_text = "\n".join([f"• {p}" for p in similar])
        
        response = messagebox.askyesnocancel(
            "Similar Products Found",
            f"Do you mean one of these products?\n\n{suggestions_text}\n\n"
            f"YES = Show options\nNO = Use '{base_product}' as new product\nCANCEL = Enter different name"
        )
        
        if response is True:
            choice = self._choose_from_suggestions(similar, base_product)
            if choice:
                versioned_choice = self.get_next_version(choice)
                existing_versions = self.get_existing_versions(choice)
                version_info = f"Existing versions: {', '.join(existing_versions)}" if existing_versions else "First recording"
                
                confirm = messagebox.askyesno(
                    "Version Confirmation",
                    f"Selected product: {choice}\n{version_info}\n\n"
                    f"New version will be: {versioned_choice}\n\nContinue?"
                )
                
                return versioned_choice if confirm else None
        elif response is False:
            new_versioned_name = f"{base_product}_v1"
            self.add_product(base_product)
            return new_versioned_name
        
        return None
    
    def _choose_from_suggestions(self, suggestions: List[str], original_query: str) -> Optional[str]:
        """Allow choosing from a list of suggestions"""
        root = tk.Tk()
        root.title("Select Product")
        root.geometry("400x300")
        
        selected_product = None
        
        tk.Label(root, text=f"Products similar to: '{original_query}'",
                font=("Arial", 12, "bold")).pack(pady=10)
        
        selection_var = tk.StringVar()
        
        frame = tk.Frame(root)
        frame.pack(pady=10, padx=20, fill='both', expand=True)
        
        for product in suggestions:
            existing_versions = self.get_existing_versions(product)
            version_text = f" ({', '.join(existing_versions)})" if existing_versions else " (new)"
            display_text = f"{product}{version_text}"
            
            tk.Radiobutton(
                frame,
                text=display_text,
                variable=selection_var,
                value=product,
                font=("Arial", 10)
            ).pack(anchor='w', pady=2)
        
        def on_select():
            nonlocal selected_product
            selected_product = selection_var.get()
            root.quit()
        
        def on_cancel():
            nonlocal selected_product
            selected_product = None
            root.quit()
        
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="Select", command=on_select,
                 bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(side='left', padx=5)
        tk.Button(btn_frame, text="Cancel", command=on_cancel,
                 bg="#f44336", fg="white", font=("Arial", 10, "bold")).pack(side='left', padx=5)
        
        try:
            root.mainloop()
            return selected_product
        finally:
            root.destroy()
