GPU Price Tracker:
This project tracks GPU prices from the first 5 pages of Amazon's Best Sellers using Python, MySQL, and Power BI.

Overview
The pipeline includes:

-	Web Scraping: Using Selenium to collect GPU product data such as price, rating, reviews, and more from Amazon.

-	Database Storage: Data is stored in a MySQL database with a structured schema (see schema.sql) that separates static product details from dynamic price changes over time.

-	Visualization: A Power BI dashboard (Amazon_GPU_Pricing_Tracker_Dashboard.pbix) connects to the database to display interactive visualizations:

•	Price trends by date and GPU model

•	Latest and lowest recorded prices

•	Comparison of current prices to MSRP

•	Filters for brand, GPU model, and time range

** This system helps e-commerce analysts and tech buyers monitor price trends and identify good deals.


Project structure:
- src/scraper/amazon.py: the Selenium scraper that collects GPU data from Amazon
- src/config.py: reads settings from environment variables (see .env.example)
- docs/Amazon_ER_Diagram.drawio.png: the original ER diagram
- dashboards/Amazon_GPU_Pricing_Tracker_Dashboard.pbix: Power BI dashboard
- schema.sql: the original MySQL schema (to be replaced by BigQuery)
- .github/workflows/scheduled-run.yml: scheduled run

Next steps:
- Move storage from MySQL to BigQuery
- Add dbt models (staging, dimensions, fact table) with tests and docs
- Schedule the full pipeline with GitHub Actions