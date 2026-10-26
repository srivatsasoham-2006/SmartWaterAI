# SmartWaterAI 💧

**IoT Water Quality Monitoring and Analysis**

SmartWaterAI is a web-based application designed to support water quality monitoring and analysis. It uses a Python Flask backend and a web interface to provide a foundation for water quality management.

## Features

- Water quality monitoring dashboard.
- Python Flask backend.
- Web-based user interface.
- Support for integrating water quality data and analysis.
- Azure deployment workflow integration through GitHub Actions.

## Technology Stack

- **Backend:** Python, Flask
- **Frontend:** HTML and CSS
- **Static Assets:** Images and other frontend resources
- **Deployment:** Microsoft Azure
- **CI/CD:** GitHub Actions

## Project Structure

```text
SmartWaterAI/
├── .github/
│   └── workflows/
├── backend/
├── static/
├── app.py
├── index.html
├── requirements.txt
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.10 or a compatible version.
- pip package manager.

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/srivatsasoham-2006/SmartWaterAI.git
   ```

2. Navigate to the project directory:

   ```bash
   cd SmartWaterAI
   ```

3. Create a virtual environment:

   ```bash
   python -m venv venv
   ```

4. Activate the environment.

   **Windows:**

   ```bash
   venv\Scripts\activate
   ```

   **Linux/macOS:**

   ```bash
   source venv/bin/activate
   ```

5. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

6. Start the application:

   ```bash
   python app.py
   ```

7. Open the local address displayed by Flask in your browser.

## Deployment

The repository includes a GitHub Actions workflow directory intended for deployment automation. Deployment requires the workflow configuration and appropriate Azure settings and credentials.

## Future Improvements

- Integration with real-time IoT water quality sensors.
- Water quality trend visualization.
- Alerts for abnormal water quality measurements.
- Historical data analysis.
- Improved monitoring and reporting capabilities.

## License

No license has been specified yet.
