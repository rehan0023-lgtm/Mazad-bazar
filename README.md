Mazad Bazaar – Online Auction Marketplace

About the Project

Mazad Bazaar is a web-based online auction marketplace developed using Python Flask and MySQL. It provides a platform where buyers and sellers can participate in online auctions.

Sellers can create auctions by uploading product details and images, while buyers can browse available products and place bids. The system also provides bidding history, auction history, notifications, and an admin section.

Objectives

- To develop an online auction platform for buyers and sellers.
- To allow sellers to create and manage auction listings.
- To enable users to place bids on available products.
- To maintain bidding records and auction history.
- To provide notifications for auction-related activities.
- To simplify the online auction management process.

Technologies Used

- Frontend: HTML, CSS, Bootstrap, JavaScript
- Backend: Python (Flask)
- Database: MySQL
- Development Tools: Visual Studio Code, XAMPP

Features

User Features

- User registration and login.
- Secure password hashing.
- Browse available auctions.
- View product details.
- Place bids on auction products.
- View personal bidding history.
- Check auction history.
- Receive notifications.

Seller Features

- Create new auctions.
- Upload product images.
- Add product descriptions and auction details.
- Manage auction listings.
- Access seller dashboard.

Admin Features

- Access the admin section.
- Manage platform activities according to administrator permissions.

Project Modules

1. User Registration and Login
2. Auction Creation
3. Product Upload
4. Browse Auctions
5. Online Bidding
6. Seller Dashboard
7. Bidding and Auction History
8. Notifications
9. Admin Management

Database

The project uses MySQL for storing and managing application data.

Database Name: "mazad_bazar"

Main database tables:

- "users" – Stores user account information.
- "auctions" – Stores product and auction details.
- "bids" – Stores bidding records.
- "notifications" – Stores user notifications.

Installation and Setup

1. Clone the Repository

git clone <your-github-repository-url>

2. Open the Project Directory

cd Mazad-Bazaar

3. Install Required Packages

pip install flask mysql-connector-python werkzeug

4. Configure MySQL Database

- Start MySQL using XAMPP.
- Open phpMyAdmin.
- Create a database named "mazad_bazar".
- Create the required tables using the project's SQL queries.
- Configure the database connection in "app.py".

5. Run the Application

python app.py

6. Open in Browser

http://127.0.0.1:5000/

Future Enhancements

- Integration of an online payment gateway.
- Email and SMS notifications.
- Advanced search and filtering.
- Real-time bidding updates.
- Mobile application development.
- Improved auction analytics.

Security

- Password hashing for user authentication.
- Parameterized SQL queries.
- Secure handling of uploaded image filenames.
- Session-based user authentication.
- Role-based administrative access.

Conclusion

Mazad Bazaar provides a digital platform for conducting online auctions. It simplifies the process of creating auctions, browsing products, placing bids, and maintaining auction records. The project demonstrates the use of Python Flask, MySQL, and frontend technologies to develop a database-driven web application.
