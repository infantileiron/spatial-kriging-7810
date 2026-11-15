import os
DATABASE_URL=os.getenv("DATABASE_URL","mysql+pymysql://spatial:spatial_demo@localhost:17731/spatial")
REDIS_URL=os.getenv("REDIS_URL","redis://redis:6379/0")
JWT_SECRET=os.getenv("JWT_SECRET","spatial-kriging-local-demo-change-before-deployment")
SEED_DEMO=os.getenv("SEED_DEMO","true").lower()=="true"
