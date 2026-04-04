flowchart TD
    %% Define Styles
    classDef client fill:#f9f6f0,stroke:#333,stroke-width:2px,color:#000
    classDef aws fill:#ff9900,stroke:#232f3e,stroke-width:2px,color:#000
    classDef k8s fill:#326ce5,stroke:#fff,stroke-width:2px,color:#fff
    classDef db fill:#336791,stroke:#fff,stroke-width:2px,color:#fff
    classDef cache fill:#dc382d,stroke:#fff,stroke-width:2px,color:#fff
    classDef broker fill:#000000,stroke:#fff,stroke-width:2px,color:#fff

    %% External
    User[React Frontend\nHosted on Vercel]:::client

    %% AWS Cloud Boundary
    subgraph AWS Cloud
        ALB[AWS Application Load Balancer]:::aws
        
        %% Kubernetes Cluster
        subgraph EKS Cluster v1.33
            Gateway[NGINX API Gateway\nJWT Verification]:::k8s
            
            subgraph Django Microservices
                Auth[Auth Service]:::k8s
                Menu[Menu Service]:::k8s
                Cart[Cart Service]:::k8s
                Order[Order Service]:::k8s
                Kitchen[Kitchen Service]:::k8s
                AI[AI Service]:::k8s
                Notify[Notification Service\nCelery Workers]:::k8s
            end
            
            Kafka[Redpanda / Kafka\nEvent Bus]:::broker
        end

        %% Managed Data Services
        DB[(AWS RDS\nPostgreSQL)]:::db
        Redis[(ElastiCache\nRedis)]:::cache
        SQS[AWS SQS\nEmail Queue]:::aws
        SES[AWS SES\nEmail Delivery]:::aws
    end

    %% Traffic Flow
    User -->|HTTPS| ALB
    ALB --> Gateway
    
    %% Gateway Routing
    Gateway -->|Trusted Internal Headers| Auth
    Gateway -->|Trusted Internal Headers| Menu
    Gateway -->|Trusted Internal Headers| Cart
    Gateway -->|Trusted Internal Headers| Order
    Gateway -->|Trusted Internal Headers| Kitchen

    %% Database & Cache Connections
    Auth & Menu & Order & Kitchen --> DB
    Cart & Gateway --> Redis
    
    %% Event Driven Flow (Pub/Sub)
    Order -->|Publish Order Event| Kafka
    Kafka -->|Consume Event| Kitchen
    Kafka -->|Consume Event| AI
    Kafka -->|Consume Event| Notify

    %% Async Email Flow
    Notify -->|Push to Queue| SQS
    SQS --> Notify
    Notify -->|Trigger Email| SES
    SES -->|Send to Customer| User