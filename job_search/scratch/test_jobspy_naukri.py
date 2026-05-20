try:
    from jobspy import scrape_jobs
    import pandas as pd
    print("JobSpy version or import successful.")
    
    # Try scraping with site_name = ["naukri"]
    try:
        df = scrape_jobs(
            site_name=["naukri"],
            search_term="Business Analyst",
            location="Chennai",
            results_wanted=5,
            verbose=1
        )
        print("Naukri results shape:", df.shape if df is not None else "None")
        if df is not None and not df.empty:
            print(df.head(2))
    except Exception as e:
        print("Naukri support error:", e)
except Exception as e:
    print("Import error:", e)
