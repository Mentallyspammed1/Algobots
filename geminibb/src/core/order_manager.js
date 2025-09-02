// src/core/order_manager.js
import { Logger } from '../utils/logger.js';
import { OrderStatus } from '../utils/constants.js';

const logger = new Logger('ORDER_MANAGER');

export class OrderManager {
    constructor() {
        this.openOrders = new Map(); // Map<orderId, orderDetails>
        logger.info('OrderManager initialized.');
    }

    /**
     * Adds a new order to the manager.
     * @param {object} orderDetails - Details of the order.
     */
    addOrder(orderDetails) {
        if (!orderDetails.orderId) {
            logger.error('Order details missing orderId:', orderDetails);
            return;
        }
        this.openOrders.set(orderDetails.orderId, {
            ...orderDetails,
            status: orderDetails.status || OrderStatus.NEW,
            createdAt: Date.now()
        });
        logger.debug(`Order ${orderDetails.orderId} added with status ${this.openOrders.get(orderDetails.orderId).status}.`);
    }

    /**
     * Updates the status or details of an existing order.
     * @param {string} orderId - The ID of the order to update.
     * @param {object} updates - Object containing fields to update.
     * @returns {boolean} - True if updated, false if order not found.
     */
    updateOrder(orderId, updates) {
        if (this.openOrders.has(orderId)) {
            const currentOrder = this.openOrders.get(orderId);
            const updatedOrder = { ...currentOrder, ...updates, lastUpdated: Date.now() };
            this.openOrders.set(orderId, updatedOrder);
            logger.debug(`Order ${orderId} updated. New status: ${updatedOrder.status}.`);
            return true;
        }
        logger.warn(`Order ${orderId} not found for update.`);
        return false;
    }

    /**
     * Retrieves an order by its ID.
     * @param {string} orderId - The ID of the order.
     * @returns {object|undefined} - The order details or undefined if not found.
     */
    getOrder(orderId) {
        return this.openOrders.get(orderId);
    }

    /**
     * Retrieves all open orders.
     * @returns {Array<object>} - An array of all orders that are not fully filled or cancelled.
     */
    getOpenOrders() {
        return Array.from(this.openOrders.values()).filter(order =>
            order.status === OrderStatus.NEW || order.status === OrderStatus.PARTIALLY_FILLED
        );
    }

    /**
     * Removes a closed/finished order from the manager.
     * @param {string} orderId - The ID of the order to remove.
     * @returns {boolean} - True if removed, false if not found.
     */
    removeOrder(orderId) {
        if (this.openOrders.delete(orderId)) {
            logger.debug(`Order ${orderId} removed.`);
            return true;
        }
        logger.warn(`Order ${orderId} not found for removal.`);
        return false;
    }
}