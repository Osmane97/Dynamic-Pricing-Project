GPU Price Tracker
This project tracks GPU prices from the first 5 pages of Amazon's Best Sellers using Python, MySQL, and Power BI.

Overview
The pipeline includes:

Web Scraping: Using Selenium to collect GPU product data such as price, rating, reviews, and more from Amazon.

Database Storage: Data is stored in a MySQL database with a structured schema (see schema.sql) that separates static product details from dynamic price changes over time.

Visualization: A Power BI dashboard (Amazon_GPU_Pricing_Tracker_Dashboard.pbix) connects to the database to display interactive visualizations:

Price trends by date and GPU model

Latest and lowest recorded prices

Comparison of current prices to MSRP

Filters for brand, GPU model, and time range

This system helps e-commerce analysts and tech buyers monitor price trends and identify good deals.


Files
scraper file that  Contains (Amazon.py) the full scraping code to extract GPU data from Amazon.

schema.sql — Defines the database tables and their relationships.

Amazon_GPU_Pricing_Tracker_Dashboard.pbix — Power BI dashboard file to explore the collected data interactively.


Next Steps
Automate the scraper to run daily using cloud services like AWS or Azure.

Expand the data sources beyond Amazon.

Add alerting features for price drops.